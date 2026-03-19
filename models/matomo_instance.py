import json
import logging
from datetime import date, timedelta
from urllib import error, parse, request

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class MatomoSyncInterrupted(Exception):
    def __init__(self, original_exc, result):
        super().__init__(str(original_exc))
        self.original_exc = original_exc
        self.result = result


class MatomoInstance(models.Model):
    _name = "matomo.instance"
    _description = "Matomo Instance"
    _order = "company_id, name"
    _check_company_auto = True

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    base_url = fields.Char(required=True)
    site_id = fields.Integer(required=True)
    api_token = fields.Char(
        required=True,
        copy=False,
        groups="matomo_analytics.group_matomo_manager",
    )
    sync_window_days = fields.Integer(default=30, required=True)
    page_limit = fields.Integer(default=25, required=True)
    last_tested_on = fields.Datetime(readonly=True)
    last_sync_started_at = fields.Datetime(readonly=True)
    last_successful_sync_at = fields.Datetime(readonly=True)
    last_sync_state = fields.Selection(
        [("success", "Success"), ("partial", "Partial"), ("failed", "Failed")],
        readonly=True,
    )
    last_sync_message = fields.Text(readonly=True)
    latest_sync_log_id = fields.Many2one(
        "matomo.sync.log",
        compute="_compute_last_sync_observability",
        readonly=True,
    )
    last_sync_warning_count = fields.Integer(
        compute="_compute_last_sync_observability",
        readonly=True,
    )
    last_sync_warning_summary = fields.Char(
        compute="_compute_last_sync_observability",
        readonly=True,
    )
    sync_log_ids = fields.One2many("matomo.sync.log", "instance_id")
    daily_metric_ids = fields.One2many("matomo.daily.metric", "instance_id")
    sync_log_count = fields.Integer(compute="_compute_counts")
    daily_metric_count = fields.Integer(compute="_compute_counts")

    _sql_constraints = [
        (
            "matomo_instance_company_site_unique",
            "unique(company_id, site_id)",
            "There is already a Matomo connection for this company and site.",
        )
    ]

    @api.constrains("base_url", "site_id", "sync_window_days", "page_limit")
    def _check_configuration_values(self):
        for record in self:
            parsed_url = parse.urlparse((record.base_url or "").strip())
            if not parsed_url.scheme or not parsed_url.netloc:
                raise ValidationError(
                    self.env._("Matomo base URL must include scheme and host.")
                )
            if record.site_id <= 0:
                raise ValidationError(self.env._("Matomo site ID must be positive."))
            if record.sync_window_days <= 0:
                raise ValidationError(
                    self.env._("Sync window days must be greater than zero.")
                )
            if record.page_limit <= 0:
                raise ValidationError(
                    self.env._("Page and ranking limits must be greater than zero.")
                )

    @api.depends("sync_log_ids", "daily_metric_ids")
    def _compute_counts(self):
        for record in self:
            record.sync_log_count = len(record.sync_log_ids)
            record.daily_metric_count = len(record.daily_metric_ids)

    @api.depends(
        "sync_log_ids.started_at",
        "sync_log_ids.warning_count",
        "sync_log_ids.warning_summary",
    )
    def _compute_last_sync_observability(self):
        for record in self:
            latest_log = self.env["matomo.sync.log"].search(
                [("instance_id", "=", record.id)],
                order="started_at desc, id desc",
                limit=1,
            )
            record.latest_sync_log_id = latest_log
            record.last_sync_warning_count = latest_log.warning_count or 0
            record.last_sync_warning_summary = latest_log.warning_summary or ""

    def action_test_connection(self):
        self.ensure_one()
        version_info = self._matomo_call("API.getMatomoVersion", include_site=False)
        self._matomo_call("SitesManager.getSiteFromId")
        self.write({"last_tested_on": fields.Datetime.now()})
        version = (
            version_info if isinstance(version_info, str) else version_info.get("value")
        )
        message = self.env._("Matomo responded correctly.")
        if version:
            message = "%s (%s)" % (message, version)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Connection successful"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_now(self):
        self.ensure_one()
        log = self._create_sync_log("manual")
        try:
            result = self._run_sync(log)
            message = self.env._("Manual sync completed successfully.")
            if result["warnings"]:
                message = self.env._("Manual sync completed with warnings.")
            log.mark_completed(result, message)
            self._update_last_sync(log)
            return self._sync_notification_action(log)
        except Exception as exc:  # pylint: disable=broad-except
            sync_error = exc if isinstance(exc, MatomoSyncInterrupted) else None
            original_exc = sync_error.original_exc if sync_error else exc
            result = sync_error.result if sync_error else self._empty_sync_result()
            partial = bool(result["imported_days"] or result["imported_records"])
            message = self._sync_failure_message(original_exc, result)
            log.mark_failed(message, result=result, partial=partial)
            self._update_last_sync(log)
            if partial:
                _logger.exception(
                    "Matomo manual sync partially completed for instance %s",
                    self.name,
                )
            else:
                _logger.exception(
                    "Matomo manual sync failed for instance %s", self.name
                )
            return self._sync_notification_action(log)

    @api.model
    def cron_sync_instances(self):
        instances = self.search([("active", "=", True)])
        for instance in instances:
            log = instance._create_sync_log("cron")
            try:
                result = instance._run_sync(log)
                message = self.env._("Scheduled sync completed successfully.")
                if result["warnings"]:
                    message = self.env._("Scheduled sync completed with warnings.")
                log.mark_completed(result, message)
                instance._update_last_sync(log)
            except Exception as exc:  # pylint: disable=broad-except
                sync_error = exc if isinstance(exc, MatomoSyncInterrupted) else None
                original_exc = sync_error.original_exc if sync_error else exc
                result = (
                    sync_error.result
                    if sync_error
                    else instance._empty_sync_result()
                )
                partial = bool(result["imported_days"] or result["imported_records"])
                message = instance._sync_failure_message(original_exc, result)
                log.mark_failed(message, result=result, partial=partial)
                instance._update_last_sync(log)
                if partial:
                    _logger.exception(
                        "Matomo scheduled sync partially completed for instance %s",
                        instance.name,
                    )
                else:
                    _logger.exception(
                        "Matomo scheduled sync failed for instance %s", instance.name
                    )
        return True

    def action_view_sync_logs(self):
        self.ensure_one()
        action = self.env.ref("matomo_analytics.matomo_sync_log_action").read()[0]
        action["domain"] = [("instance_id", "=", self.id)]
        action["context"] = {"search_default_instance_id": self.id}
        return action

    def action_open_latest_sync_log(self):
        self.ensure_one()
        if not self.latest_sync_log_id:
            return self.action_view_sync_logs()
        action = self.env.ref("matomo_analytics.matomo_sync_log_action").read()[0]
        action.update(
            {
                "view_mode": "form",
                "views": [(False, "form")],
                "res_id": self.latest_sync_log_id.id,
                "domain": [],
                "context": {},
            }
        )
        return action

    def action_open_dashboard(self):
        self.ensure_one()
        return self.env["matomo.analytics.dashboard"].action_open_dashboard(
            instance=self
        )

    def _create_sync_log(self, trigger: str):
        self.ensure_one()
        today = fields.Date.context_today(self)
        date_from = today - timedelta(days=self.sync_window_days - 1)
        log = self.env["matomo.sync.log"].create(
            {
                "name": self.env._("Matomo Sync %s") % today,
                "company_id": self.company_id.id,
                "instance_id": self.id,
                "trigger": trigger,
                "date_from": date_from,
                "date_to": today,
            }
        )
        self.write({"last_sync_started_at": log.started_at})
        return log

    def _run_sync(self, log):
        self.ensure_one()
        result = self._empty_sync_result()
        current_day = log.date_from
        while current_day <= log.date_to:
            try:
                with self.env.cr.savepoint():
                    payload, warnings = self._fetch_day_payload(current_day)
                    day_counts = self._replace_day_payload(current_day, payload)
            except Exception as exc:
                raise MatomoSyncInterrupted(exc, result) from exc
            result["imported_days"] += 1
            for count_key, count_value in day_counts.items():
                result[count_key] += count_value
            result["imported_records"] += sum(day_counts.values())
            if warnings:
                result["warnings"].extend(
                    self._format_day_warnings(current_day, warnings)
                )
            current_day += timedelta(days=1)
        return result

    def _fetch_day_payload(self, metric_date: date):
        warnings = []
        report_specs = self._bulk_report_specs()
        urls = [
            self._build_bulk_subrequest(method_name, metric_date)
            for _key, method_name, _type, _label in report_specs
        ]
        reports = self._matomo_bulk_call(urls)
        payload = {}
        for index, (key, _method_name, expected_type, label) in enumerate(report_specs):
            payload[key], report_warnings = self._extract_bulk_report(
                reports, index, expected_type, label
            )
            warnings.extend(report_warnings)
        goal_summary, goal_summary_warnings = self._safe_matomo_call(
            self.env._("Goal summary"),
            "Goals.get",
            {},
            date=metric_date.isoformat(),
            period="day",
            include_site=True,
            idGoal="all",
        )
        goal_report, goal_report_warnings = self._safe_matomo_call(
            self.env._("Goal breakdown"),
            "API.getProcessedReport",
            {},
            date=metric_date.isoformat(),
            period="day",
            include_site=True,
            apiModule="Goals",
            apiAction="get",
            idGoal="all",
        )
        warnings.extend(goal_summary_warnings)
        warnings.extend(goal_report_warnings)
        payload.update(
            {
                "goal_summary": goal_summary,
                "goal_report": goal_report,
            }
        )
        return payload, warnings

    def _replace_day_payload(self, metric_date: date, payload: dict):
        self.ensure_one()
        self.env["matomo.daily.metric"].search(
            [("instance_id", "=", self.id), ("date", "=", metric_date)]
        ).unlink()
        self.env["matomo.channel.metric"].search(
            [("instance_id", "=", self.id), ("date", "=", metric_date)]
        ).unlink()
        self.env["matomo.country.metric"].search(
            [("instance_id", "=", self.id), ("date", "=", metric_date)]
        ).unlink()
        self.env["matomo.referrer.metric"].search(
            [("instance_id", "=", self.id), ("date", "=", metric_date)]
        ).unlink()
        self.env["matomo.page.metric"].search(
            [("instance_id", "=", self.id), ("date", "=", metric_date)]
        ).unlink()
        self.env["matomo.goal.metric"].search(
            [("instance_id", "=", self.id), ("date", "=", metric_date)]
        ).unlink()

        channel_values = self._prepare_channel_values(metric_date, payload["channels"])
        country_values = self._prepare_country_values(metric_date, payload["countries"])
        referrer_values = self._prepare_referrer_values(
            metric_date, payload["referrers"]
        )
        page_values = (
            self._prepare_page_values(metric_date, payload["pages"], "page")
            + self._prepare_page_values(
                metric_date, payload["landing_pages"], "landing"
            )
            + self._prepare_page_values(metric_date, payload["exit_pages"], "exit")
        )
        goal_values = self._prepare_goal_values(
            metric_date, payload["goal_report"], payload["goal_summary"]
        )

        if channel_values:
            self.env["matomo.channel.metric"].create(channel_values)
        if country_values:
            self.env["matomo.country.metric"].create(country_values)
        if referrer_values:
            self.env["matomo.referrer.metric"].create(referrer_values)
        if page_values:
            self.env["matomo.page.metric"].create(page_values)
        if goal_values:
            self.env["matomo.goal.metric"].create(goal_values)

        top_channel = ""
        if channel_values:
            top_channel = max(channel_values, key=lambda val: val["sessions"]).get(
                "channel_name", ""
            )

        goal_summary = (
            payload["goal_summary"] if isinstance(payload["goal_summary"], dict) else {}
        )
        conversions = self._metric_number(goal_summary, "nb_conversions")
        if not conversions and goal_values:
            conversions = sum(goal["conversions"] for goal in goal_values)

        self.env["matomo.daily.metric"].create(
            {
                "company_id": self.company_id.id,
                "instance_id": self.id,
                "date": metric_date,
                "visitors": self._metric_number(payload["summary"], "nb_visitors"),
                "sessions": self._metric_number(payload["summary"], "nb_visits"),
                "conversions": conversions,
                "bounce_rate": self._metric_percent(payload["summary"], "bounce_rate"),
                "avg_session_duration": self._metric_duration(
                    payload["summary"], "avg_time_on_site"
                ),
                "top_channel": top_channel,
            }
        )
        return {
            "daily_records": 1,
            "channel_records": len(channel_values),
            "country_records": len(country_values),
            "referrer_records": len(referrer_values),
            "page_records": len(page_values),
            "goal_records": len(goal_values),
        }

    def _prepare_channel_values(self, metric_date: date, rows):
        return [
            {
                "company_id": self.company_id.id,
                "instance_id": self.id,
                "date": metric_date,
                "channel_name": row.get("label") or self.env._("Unknown"),
                "sessions": self._metric_number(row, "nb_visits"),
                "visitors": self._metric_number(row, "nb_visitors", "nb_uniq_visitors"),
                "conversions": self._metric_number(
                    row, "nb_conversions", "nb_visits_converted"
                ),
                "bounce_rate": self._metric_percent(row, "bounce_rate"),
            }
            for row in self._clean_rows(rows)
        ]

    def _prepare_country_values(self, metric_date: date, rows):
        values = []
        for row in self._clean_rows(rows):
            values.append(
                {
                    "company_id": self.company_id.id,
                    "instance_id": self.id,
                    "date": metric_date,
                    "country_code": row.get("code") or row.get("codeCountry") or "",
                    "country_name": row.get("label") or self.env._("Unknown"),
                    "visitors": self._metric_number(
                        row, "nb_visitors", "nb_uniq_visitors"
                    ),
                    "sessions": self._metric_number(row, "nb_visits"),
                    "conversions": self._metric_number(
                        row, "nb_conversions", "nb_visits_converted"
                    ),
                    "bounce_rate": self._metric_percent(row, "bounce_rate"),
                }
            )
        return values

    def _prepare_referrer_values(self, metric_date: date, rows):
        values = []
        for row in self._clean_rows(rows):
            values.append(
                {
                    "company_id": self.company_id.id,
                    "instance_id": self.id,
                    "date": metric_date,
                    "referrer_name": row.get("label") or self.env._("Unknown"),
                    "referrer_type": row.get("type") or "",
                    "visitors": self._metric_number(
                        row, "nb_visitors", "nb_uniq_visitors"
                    ),
                    "sessions": self._metric_number(row, "nb_visits"),
                    "conversions": self._metric_number(
                        row, "nb_conversions", "nb_visits_converted"
                    ),
                }
            )
        return values

    def _prepare_page_values(self, metric_date: date, rows, metric_type: str):
        values = []
        for row in self._clean_rows(rows):
            values.append(
                {
                    "company_id": self.company_id.id,
                    "instance_id": self.id,
                    "date": metric_date,
                    "metric_type": metric_type,
                    "page_label": row.get("label") or self.env._("Unknown"),
                    "page_url": row.get("url") or row.get("label") or "",
                    "visitors": self._metric_number(
                        row, "nb_visitors", "nb_uniq_visitors"
                    ),
                    "visits": self._metric_number(
                        row, "nb_visits", "entry_nb_visits", "exit_nb_visits"
                    ),
                    "pageviews": self._metric_number(row, "nb_hits", "nb_pageviews"),
                    "entrances": self._metric_number(row, "entry_nb_visits"),
                    "exits": self._metric_number(row, "exit_nb_visits"),
                    "bounce_rate": self._metric_percent(row, "bounce_rate"),
                    "exit_rate": self._metric_percent(row, "exit_rate"),
                    "avg_time_on_page": self._metric_duration(
                        row, "avg_time_on_page", "avg_time_generation"
                    ),
                }
            )
        return values

    def _prepare_goal_values(self, metric_date: date, goal_report, goal_summary):
        values = []
        report_rows = []
        if isinstance(goal_report, dict):
            report_rows = (
                goal_report.get("reportData")
                or goal_report.get("report_data")
                or goal_report.get("rows")
                or []
            )
        elif isinstance(goal_report, list):
            report_rows = goal_report
        for row in self._clean_rows(report_rows):
            label = row.get("label") or self.env._("Goal")
            values.append(
                {
                    "company_id": self.company_id.id,
                    "instance_id": self.id,
                    "date": metric_date,
                    "goal_key": str(row.get("idsubdatatable") or label),
                    "goal_name": label,
                    "conversions": self._metric_number(row, "nb_conversions"),
                    "conversion_rate": self._metric_percent(row, "conversion_rate"),
                    "revenue": self._metric_float(row, "revenue"),
                }
            )
        if not values and isinstance(goal_summary, dict):
            conversions = self._metric_number(goal_summary, "nb_conversions")
            if conversions:
                values.append(
                    {
                        "company_id": self.company_id.id,
                        "instance_id": self.id,
                        "date": metric_date,
                        "goal_key": "all",
                        "goal_name": self.env._("All Goals"),
                        "conversions": conversions,
                        "conversion_rate": self._metric_percent(
                            goal_summary, "conversion_rate"
                        ),
                        "revenue": self._metric_float(goal_summary, "revenue"),
                    }
                )
        return values

    def _build_bulk_subrequest(self, method_name: str, metric_date: date, **extra):
        params = {
            "method": method_name,
            "idSite": self.site_id,
            "period": "day",
            "date": metric_date.isoformat(),
            "filter_truncate": self.page_limit,
            "flat": 1,
        }
        params.update(extra)
        return parse.urlencode(params, doseq=True)

    def _matomo_bulk_call(self, urls):
        payload = {
            "module": "API",
            "method": "API.getBulkRequest",
            "format": "JSON",
            "token_auth": self.api_token,
        }
        for index, subrequest in enumerate(urls):
            payload[f"urls[{index}]"] = subrequest
        response = self._do_post(payload)
        if not isinstance(response, list):
            raise UserError(self.env._("Matomo bulk response was not a list."))
        return response

    def _bulk_report_specs(self):
        return [
            ("summary", "VisitsSummary.get", dict, self.env._("Summary")),
            ("channels", "Referrers.getReferrerType", list, self.env._("Channels")),
            ("pages", "Actions.getPageUrls", list, self.env._("Top pages")),
            (
                "landing_pages",
                "Actions.getEntryPageUrls",
                list,
                self.env._("Landing pages"),
            ),
            ("exit_pages", "Actions.getExitPageUrls", list, self.env._("Exit pages")),
            ("countries", "UserCountry.getCountry", list, self.env._("Countries")),
            ("referrers", "Referrers.getAll", list, self.env._("Referrers")),
        ]

    def _empty_sync_result(self):
        return {
            "imported_days": 0,
            "imported_records": 0,
            "daily_records": 0,
            "channel_records": 0,
            "country_records": 0,
            "referrer_records": 0,
            "page_records": 0,
            "goal_records": 0,
            "warnings": [],
        }

    def _extract_bulk_report(self, reports, index: int, expected_type, label: str):
        default_value = {} if expected_type is dict else []
        if index >= len(reports):
            return default_value, [
                self.env._("%s report missing from bulk response.") % label
            ]
        report = reports[index]
        if isinstance(report, dict) and report.get("result") == "error":
            message = report.get("message") or self.env._("Unknown error")
            return default_value, [
                self.env._("%s report failed: %s") % (label, message)
            ]
        if isinstance(report, expected_type):
            return report, []
        if report in (None, False, ""):
            return default_value, [self.env._("%s report was empty.") % label]
        return default_value, [
            self.env._("%s report had unexpected payload type %s.")
            % (label, type(report).__name__)
        ]

    def _safe_matomo_call(self, label: str, method_name: str, default_value, **params):
        try:
            return self._matomo_call(method_name, **params), []
        except UserError as exc:
            _logger.warning(
                "Matomo %s unavailable for site %s: %s",
                label.lower(),
                self.site_id,
                exc,
            )
            return (
                default_value,
                [
                    self.env._("%s unavailable: %s")
                    % (label, self._exception_message(exc))
                ],
            )

    def _matomo_call(self, method_name: str, include_site: bool = True, **params):
        payload = {
            "module": "API",
            "method": method_name,
            "format": "JSON",
            "token_auth": self.api_token,
        }
        if include_site:
            payload["idSite"] = self.site_id
        payload.update(params)
        return self._do_post(payload)

    def _do_post(self, payload: dict):
        endpoint = self._endpoint_url()
        encoded = parse.urlencode(payload, doseq=True).encode()
        req = request.Request(
            endpoint,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30) as response:  # nosec B310
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            message = (
                exc.read().decode("utf-8", errors="ignore")
                if exc.fp
                else str(exc)
            )
            raise UserError(
                self.env._("Matomo responded with HTTP %s: %s")
                % (exc.code, message)
            ) from exc
        except error.URLError as exc:
            raise UserError(
                self.env._("Could not reach Matomo: %s") % (exc.reason or exc)
            ) from exc

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise UserError(
                self.env._("Matomo returned an invalid JSON response.")
            ) from exc

        if isinstance(data, dict) and data.get("result") == "error":
            raise UserError(data.get("message") or self.env._("Matomo request failed."))
        return data

    def _endpoint_url(self):
        base = (self.base_url or "").strip().rstrip("/")
        parsed = parse.urlparse(base)
        if not parsed.scheme or not parsed.netloc:
            raise UserError(self.env._("Matomo base URL must be a valid absolute URL."))
        return "%s/index.php" % base

    def _clean_rows(self, rows):
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _metric_number(self, data, *keys):
        return int(round(self._metric_float(data, *keys)))

    def _metric_float(self, data, *keys):
        if not isinstance(data, dict):
            return 0.0
        for key in keys:
            if key in data and data[key] not in (None, "", False):
                return self._coerce_float(data[key])
        return 0.0

    def _metric_percent(self, data, *keys):
        return self._metric_float(data, *keys)

    def _metric_duration(self, data, *keys):
        return self._metric_float(data, *keys)

    def _coerce_float(self, value):
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip().replace("%", "").replace(",", "")
            if cleaned.count(":") == 2:
                try:
                    hours, minutes, seconds = [
                        int(chunk) for chunk in cleaned.split(":")
                    ]
                except ValueError:
                    return 0.0
                return float(hours * 3600 + minutes * 60 + seconds)
            if cleaned.count(":") == 1:
                try:
                    minutes, seconds = [int(chunk) for chunk in cleaned.split(":")]
                except ValueError:
                    return 0.0
                return float(minutes * 60 + seconds)
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        return 0.0

    def _format_day_warnings(self, metric_date: date, warnings):
        return [
            self.env._("%s: %s") % (metric_date.isoformat(), warning)
            for warning in warnings
        ]

    def _sync_failure_message(self, exc, result):
        message = self._exception_message(exc)
        if result["imported_days"] or result["imported_records"]:
            return self.env._(
                "Sync stopped after importing %s days and %s records: %s"
            ) % (result["imported_days"], result["imported_records"], message)
        return message

    def _update_last_sync(self, log):
        values = {
            "last_sync_state": log.state,
            "last_sync_message": self._instance_sync_message(log),
        }
        if log.state == "success":
            values["last_successful_sync_at"] = log.finished_at
        self.write(values)

    def _instance_sync_message(self, log):
        message_parts = [log.message or ""]
        if log.warning_count:
            message_parts.append(
                self.env._("%s warnings recorded. Review the sync log for details.")
                % log.warning_count
            )
        return "\n".join(part for part in message_parts if part)

    def _sync_notification_action(self, log):
        if log.state == "success":
            title = self.env._("Sync complete")
            message = self.env._("Imported %s days and %s records.") % (
                log.imported_days,
                log.imported_records,
            )
            notif_type = "success"
            sticky = False
        elif log.state == "partial":
            title = self.env._("Sync partially completed")
            message = self.env._(
                "Imported %s days and %s records with %s warnings."
            ) % (log.imported_days, log.imported_records, log.warning_count)
            notif_type = "warning"
            sticky = True
        else:
            title = self.env._("Sync failed")
            message = log.message
            notif_type = "danger"
            sticky = True
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": notif_type,
                "sticky": sticky,
            },
        }

    def _exception_message(self, exc):
        if isinstance(exc, UserError):
            return exc.args[0]
        return str(exc)
