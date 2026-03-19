import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MatomoSyncLog(models.Model):
    _name = "matomo.sync.log"
    _description = "Matomo Sync Log"
    _order = "started_at desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: self.env._("New Sync"))
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    instance_id = fields.Many2one(
        "matomo.instance",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("running", "Running"),
            ("success", "Success"),
            ("partial", "Partial"),
            ("failed", "Failed"),
        ],
        required=True,
        default="running",
        index=True,
    )
    trigger = fields.Selection(
        [("manual", "Manual"), ("cron", "Scheduled")],
        required=True,
        default="manual",
    )
    started_at = fields.Datetime(required=True, default=fields.Datetime.now)
    finished_at = fields.Datetime()
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    imported_days = fields.Integer(default=0)
    imported_records = fields.Integer(default=0)
    daily_records = fields.Integer(default=0)
    channel_records = fields.Integer(default=0)
    country_records = fields.Integer(default=0)
    referrer_records = fields.Integer(default=0)
    page_records = fields.Integer(default=0)
    goal_records = fields.Integer(default=0)
    warning_count = fields.Integer(default=0)
    warning_summary = fields.Char(compute="_compute_warning_summary")
    warning_details = fields.Text()
    message = fields.Text()

    @api.depends("warning_count", "warning_details")
    def _compute_warning_summary(self):
        for record in self:
            warnings = [
                line.strip()
                for line in (record.warning_details or "").splitlines()
                if line.strip()
            ]
            if not warnings:
                record.warning_summary = ""
            elif len(warnings) == 1:
                record.warning_summary = warnings[0]
            else:
                record.warning_summary = "%s (+%s more)" % (
                    warnings[0],
                    len(warnings) - 1,
                )

    def _result_values(self, result):
        result = result or {}
        warnings = result.get("warnings") or []
        return {
            "imported_days": result.get("imported_days", 0),
            "imported_records": result.get("imported_records", 0),
            "daily_records": result.get("daily_records", 0),
            "channel_records": result.get("channel_records", 0),
            "country_records": result.get("country_records", 0),
            "referrer_records": result.get("referrer_records", 0),
            "page_records": result.get("page_records", 0),
            "goal_records": result.get("goal_records", 0),
            "warning_count": len(warnings),
            "warning_details": "\n".join(warnings),
        }

    def mark_completed(self, result, message: str = ""):
        self.ensure_one()
        state = "partial" if result.get("warnings") else "success"
        values = {
            "state": state,
            "finished_at": fields.Datetime.now(),
            "message": message,
        }
        values.update(self._result_values(result))
        self.write(values)
        log_method = _logger.warning if state == "partial" else _logger.info
        log_method(
            "Matomo sync %s for instance %s (%s days, %s records, %s warnings)",
            state,
            self.instance_id.display_name,
            values["imported_days"],
            values["imported_records"],
            values["warning_count"],
        )

    def mark_failed(self, message: str, result=None, partial: bool = False):
        self.ensure_one()
        state = "partial" if partial else "failed"
        values = {
            "state": state,
            "finished_at": fields.Datetime.now(),
            "message": message,
        }
        values.update(self._result_values(result))
        self.write(values)
        log_method = _logger.warning if state == "partial" else _logger.error
        log_method(
            "Matomo sync %s for instance %s: %s",
            state,
            self.instance_id.display_name,
            message,
        )
