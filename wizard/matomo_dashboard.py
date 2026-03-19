from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


DATE_RANGE_PRESET_SELECTION = [
    ("7d", "Last 7 days"),
    ("30d", "Last 30 days"),
    ("90d", "Last 90 days"),
    ("custom", "Custom"),
]

COMPARISON_MODE_SELECTION = [
    ("previous_period", "Previous period"),
    ("custom", "Custom range"),
]

PRESET_DAY_MAPPING = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
}


class MatomoAnalyticsDashboard(models.TransientModel):
    _name = "matomo.analytics.dashboard"
    _description = "Matomo Analytics Insights"

    instance_id = fields.Many2one(
        "matomo.instance",
        required=True,
        default=lambda self: self._default_instance(),
    )
    company_id = fields.Many2one(
        "res.company",
        related="instance_id.company_id",
        readonly=True,
    )
    date_range_preset = fields.Selection(
        DATE_RANGE_PRESET_SELECTION,
        string="Preset",
        required=True,
        default="30d",
    )
    date_from = fields.Date(required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(required=True, default=lambda self: fields.Date.context_today(self))
    comparison_enabled = fields.Boolean(
        string="Compare",
        default=True,
    )
    comparison_mode = fields.Selection(
        COMPARISON_MODE_SELECTION,
        string="Comparison",
        required=True,
        default="previous_period",
    )
    compare_date_from = fields.Date()
    compare_date_to = fields.Date()
    selected_range_label = fields.Char(string="Current Range", compute="_compute_metrics")
    compare_range_label = fields.Char(
        string="Comparison Range", compute="_compute_metrics"
    )
    report_scope_summary = fields.Char(compute="_compute_metrics")
    comparison_scope_summary = fields.Char(compute="_compute_metrics")
    last_successful_sync_at = fields.Datetime(compute="_compute_metrics")
    last_sync_state = fields.Selection(
        [("success", "Success"), ("partial", "Partial"), ("failed", "Failed")],
        compute="_compute_metrics",
    )
    last_sync_message = fields.Text(compute="_compute_metrics")
    sync_status_summary = fields.Text(compute="_compute_metrics")
    data_quality_summary = fields.Text(compute="_compute_metrics")
    latest_sync_log_id = fields.Many2one("matomo.sync.log", compute="_compute_metrics")
    last_sync_warning_count = fields.Integer(compute="_compute_metrics")
    last_sync_warning_summary = fields.Char(compute="_compute_metrics")
    latest_available_date = fields.Date(
        string="Latest Stored Day", compute="_compute_metrics"
    )
    available_day_count = fields.Integer(string="Stored Days", compute="_compute_metrics")
    expected_day_count = fields.Integer(
        string="Expected Days", compute="_compute_metrics"
    )
    total_visitors = fields.Integer(compute="_compute_metrics")
    total_sessions = fields.Integer(compute="_compute_metrics")
    total_conversions = fields.Float(compute="_compute_metrics")
    bounce_rate = fields.Float(compute="_compute_metrics")
    conversion_rate = fields.Float(string="Conversion Rate", compute="_compute_metrics")
    top_channel = fields.Char(compute="_compute_metrics")
    compare_visitors = fields.Integer(
        string="Comparison Visitors", compute="_compute_metrics"
    )
    compare_sessions = fields.Integer(
        string="Comparison Sessions", compute="_compute_metrics"
    )
    compare_conversions = fields.Float(
        string="Comparison Conversions", compute="_compute_metrics"
    )
    compare_bounce_rate = fields.Float(
        string="Comparison Bounce Rate", compute="_compute_metrics"
    )
    compare_conversion_rate = fields.Float(
        string="Comparison Conversion Rate", compute="_compute_metrics"
    )
    visitors_delta = fields.Float(string="Visitors Delta", compute="_compute_metrics")
    sessions_delta = fields.Float(string="Sessions Delta", compute="_compute_metrics")
    conversions_delta = fields.Float(
        string="Conversions Delta", compute="_compute_metrics"
    )
    bounce_rate_delta = fields.Float(
        string="Bounce Rate Points", compute="_compute_metrics"
    )
    conversion_rate_delta = fields.Float(
        string="Conversion Rate Points", compute="_compute_metrics"
    )
    change_summary = fields.Text(compute="_compute_metrics")
    next_step_summary = fields.Text(compute="_compute_metrics")
    top_channels_summary = fields.Text(compute="_compute_metrics")
    top_referrers_summary = fields.Text(compute="_compute_metrics")
    top_countries_summary = fields.Text(compute="_compute_metrics")
    top_pages_summary = fields.Text(compute="_compute_metrics")
    top_landing_pages_summary = fields.Text(compute="_compute_metrics")
    top_exit_pages_summary = fields.Text(compute="_compute_metrics")
    top_goals_summary = fields.Text(compute="_compute_metrics")

    @api.model
    def _default_instance(self):
        return self.env["matomo.instance"].search(
            [("company_id", "in", self.env.companies.ids), ("active", "=", True)],
            limit=1,
        )

    @api.model
    def _default_date_from(self):
        return fields.Date.context_today(self) - timedelta(days=29)

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        normalized_vals_list = []
        for vals in vals_list:
            normalized_vals = dict(vals)
            preset = normalized_vals.get("date_range_preset")
            preset_days = PRESET_DAY_MAPPING.get(preset)
            if preset_days and (
                "date_from" not in normalized_vals or "date_to" not in normalized_vals
            ):
                normalized_vals.setdefault("date_to", today)
                normalized_vals.setdefault(
                    "date_from",
                    today - timedelta(days=preset_days - 1),
                )
            normalized_vals_list.append(normalized_vals)
        return super().create(normalized_vals_list)

    @api.onchange("date_range_preset")
    def _onchange_date_range_preset(self):
        for wizard in self:
            wizard._apply_date_range_preset()

    @api.onchange("date_from", "date_to")
    def _onchange_dates(self):
        for wizard in self:
            wizard.date_range_preset = wizard._matching_date_range_preset()

    @api.depends(
        "instance_id",
        "date_range_preset",
        "date_from",
        "date_to",
        "comparison_enabled",
        "comparison_mode",
        "compare_date_from",
        "compare_date_to",
    )
    def _compute_metrics(self):
        daily_metric_model = self.env["matomo.daily.metric"]
        channel_metric_model = self.env["matomo.channel.metric"]
        country_metric_model = self.env["matomo.country.metric"]
        referrer_metric_model = self.env["matomo.referrer.metric"]
        page_metric_model = self.env["matomo.page.metric"]
        goal_metric_model = self.env["matomo.goal.metric"]
        for wizard in self:
            wizard._reset_dashboard_values()
            wizard.last_successful_sync_at = wizard.instance_id.last_successful_sync_at
            wizard.last_sync_state = wizard.instance_id.last_sync_state
            wizard.last_sync_message = wizard.instance_id.last_sync_message
            wizard.latest_sync_log_id = wizard.instance_id.latest_sync_log_id
            wizard.last_sync_warning_count = wizard.instance_id.last_sync_warning_count
            wizard.last_sync_warning_summary = (
                wizard.instance_id.last_sync_warning_summary
            )
            if not wizard.instance_id or not wizard.date_from or not wizard.date_to:
                wizard.sync_status_summary = wizard._build_sync_status_summary()
                continue

            compare_date_from, compare_date_to = wizard._comparison_range()
            current_domain = wizard._metric_domain(wizard.date_from, wizard.date_to)
            current_daily_metrics = daily_metric_model.search(current_domain)
            wizard.selected_range_label = wizard._format_range_label(
                wizard.date_from,
                wizard.date_to,
                preset=wizard.date_range_preset,
            )
            wizard.report_scope_summary = wizard.env._(
                "Connection %s. Showing stored analytics from %s to %s."
            ) % (wizard.instance_id.name, wizard.date_from, wizard.date_to)
            wizard.total_visitors = int(sum(current_daily_metrics.mapped("visitors")))
            wizard.total_sessions = int(sum(current_daily_metrics.mapped("sessions")))
            wizard.total_conversions = sum(current_daily_metrics.mapped("conversions"))
            wizard.bounce_rate = wizard._weighted_bounce_rate(current_daily_metrics)
            wizard.conversion_rate = wizard._conversion_rate(
                wizard.total_conversions, wizard.total_sessions
            )
            wizard.expected_day_count = wizard._period_day_count(
                wizard.date_from, wizard.date_to
            )
            wizard.available_day_count = len(current_daily_metrics)
            wizard.latest_available_date = (
                current_daily_metrics[:1].date if current_daily_metrics else False
            )

            channel_records = channel_metric_model.search(current_domain)
            country_records = country_metric_model.search(current_domain)
            referrer_records = referrer_metric_model.search(current_domain)
            page_records = page_metric_model.search(current_domain)
            goal_records = goal_metric_model.search(current_domain)

            wizard.top_channels_summary, wizard.top_channel = (
                wizard._build_channel_summary(channel_records)
            )
            wizard.top_referrers_summary = wizard._build_referrer_summary(
                referrer_records
            )
            wizard.top_countries_summary = wizard._build_country_summary(country_records)
            wizard.top_pages_summary = wizard._build_page_summary(
                page_records.filtered(lambda record: record.metric_type == "page"),
                metric_type="page",
            )
            wizard.top_landing_pages_summary = wizard._build_page_summary(
                page_records.filtered(lambda record: record.metric_type == "landing"),
                metric_type="landing",
            )
            wizard.top_exit_pages_summary = wizard._build_page_summary(
                page_records.filtered(lambda record: record.metric_type == "exit"),
                metric_type="exit",
            )
            wizard.top_goals_summary = wizard._build_goal_summary(goal_records)

            if compare_date_from and compare_date_to:
                wizard.compare_range_label = wizard._format_range_label(
                    compare_date_from,
                    compare_date_to,
                    preset=(
                        "previous_period"
                        if wizard.comparison_mode == "previous_period"
                        else "custom"
                    ),
                )
                wizard.comparison_scope_summary = wizard.env._(
                    "Comparison period from %s to %s."
                ) % (compare_date_from, compare_date_to)
                compare_domain = wizard._metric_domain(compare_date_from, compare_date_to)
                compare_metrics = daily_metric_model.search(compare_domain)
                wizard.compare_visitors = int(sum(compare_metrics.mapped("visitors")))
                wizard.compare_sessions = int(sum(compare_metrics.mapped("sessions")))
                wizard.compare_conversions = sum(compare_metrics.mapped("conversions"))
                wizard.compare_bounce_rate = wizard._weighted_bounce_rate(compare_metrics)
                wizard.compare_conversion_rate = wizard._conversion_rate(
                    wizard.compare_conversions,
                    wizard.compare_sessions,
                )
                wizard.visitors_delta = wizard._delta_percent(
                    wizard.total_visitors, wizard.compare_visitors
                )
                wizard.sessions_delta = wizard._delta_percent(
                    wizard.total_sessions, wizard.compare_sessions
                )
                wizard.conversions_delta = wizard._delta_percent(
                    wizard.total_conversions, wizard.compare_conversions
                )
                wizard.bounce_rate_delta = wizard.bounce_rate - wizard.compare_bounce_rate
                wizard.conversion_rate_delta = (
                    wizard.conversion_rate - wizard.compare_conversion_rate
                )

            wizard.data_quality_summary = wizard._build_data_quality_summary(
                current_daily_metrics,
                compare_date_from,
                compare_date_to,
            )
            wizard.sync_status_summary = wizard._build_sync_status_summary(
                current_daily_metrics
            )
            wizard.change_summary = wizard._build_change_summary()
            wizard.next_step_summary = wizard._build_next_step_summary()

    def _reset_dashboard_values(self):
        self.ensure_one()
        self.selected_range_label = ""
        self.compare_range_label = ""
        self.report_scope_summary = ""
        self.comparison_scope_summary = ""
        self.sync_status_summary = ""
        self.data_quality_summary = ""
        self.latest_available_date = False
        self.available_day_count = 0
        self.expected_day_count = 0
        self.total_visitors = 0
        self.total_sessions = 0
        self.total_conversions = 0
        self.bounce_rate = 0
        self.conversion_rate = 0
        self.top_channel = ""
        self.compare_visitors = 0
        self.compare_sessions = 0
        self.compare_conversions = 0
        self.compare_bounce_rate = 0
        self.compare_conversion_rate = 0
        self.visitors_delta = 0
        self.sessions_delta = 0
        self.conversions_delta = 0
        self.bounce_rate_delta = 0
        self.conversion_rate_delta = 0
        self.change_summary = ""
        self.next_step_summary = ""
        self.top_channels_summary = ""
        self.top_referrers_summary = ""
        self.top_countries_summary = ""
        self.top_pages_summary = ""
        self.top_landing_pages_summary = ""
        self.top_exit_pages_summary = ""
        self.top_goals_summary = ""

    def action_refresh(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(self.env._("The start date must be before the end date."))
        compare_date_from, compare_date_to = self._comparison_range()
        if compare_date_from and compare_date_to and compare_date_from > compare_date_to:
            raise UserError(
                self.env._("The comparison start date must be before the end date.")
            )
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    @api.model
    def action_open_dashboard(self, instance=None, wizard=None):
        instance = instance or self._default_instance()
        if not instance:
            return self._action_open_connection_setup()
        wizard = wizard or self.create(
            {
                "instance_id": instance.id,
                "comparison_enabled": True,
                "comparison_mode": "previous_period",
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Matomo Insights"),
            "res_model": "matomo.analytics.dashboard",
            "view_mode": "form",
            "res_id": wizard.id,
            "target": "current",
        }

    @api.model
    def _action_open_connection_setup(self):
        instance_count = self.env["matomo.instance"].search_count(
            [("company_id", "in", self.env.companies.ids)]
        )
        if instance_count:
            return self.env.ref("matomo_analytics.matomo_instance_action").read()[0]
        form_view = self.env.ref("matomo_analytics.matomo_instance_view_form")
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Create Matomo Connection"),
            "res_model": "matomo.instance",
            "view_mode": "form",
            "views": [(form_view.id, "form")],
            "target": "current",
            "context": {
                "default_company_id": self.env.company.id,
            },
        }

    def action_sync_now(self):
        self.ensure_one()
        return self.instance_id.action_sync_now()

    def action_open_latest_sync_log(self):
        self.ensure_one()
        return self.instance_id.action_open_latest_sync_log()

    def action_open_daily_trend(self):
        self.ensure_one()
        return self._scoped_report_action(
            "matomo_analytics.matomo_daily_metric_action",
            self.env._("Daily Trend"),
            search_defaults={"group_by_date": 1},
        )

    def action_open_traffic_report(self):
        self.ensure_one()
        return self._scoped_report_action(
            "matomo_analytics.matomo_channel_metric_action",
            self.env._("Traffic Channels"),
            search_defaults={"group_by_channel": 1},
        )

    def action_open_country_report(self):
        self.ensure_one()
        return self._scoped_report_action(
            "matomo_analytics.matomo_country_metric_action",
            self.env._("Traffic Countries"),
            search_defaults={"group_by_country": 1},
        )

    def action_open_referrer_report(self):
        self.ensure_one()
        return self._scoped_report_action(
            "matomo_analytics.matomo_referrer_metric_action",
            self.env._("Traffic Referrers"),
            search_defaults={"group_by_referrer": 1},
        )

    def action_open_content_report(self):
        self.ensure_one()
        return self._scoped_report_action(
            "matomo_analytics.matomo_page_metric_action",
            self.env._("Content Reporting"),
            extra=[("metric_type", "in", ["page", "landing", "exit"])],
            search_defaults={"group_by_metric_type": 1},
        )

    def action_open_top_pages_report(self):
        self.ensure_one()
        return self._scoped_report_action(
            "matomo_analytics.matomo_page_metric_action",
            self.env._("Top Pages"),
            extra=[("metric_type", "=", "page")],
            search_defaults={"filter_page": 1},
        )

    def action_open_landing_page_report(self):
        self.ensure_one()
        return self._scoped_report_action(
            "matomo_analytics.matomo_page_metric_action",
            self.env._("Landing Pages"),
            extra=[("metric_type", "=", "landing")],
            search_defaults={"filter_landing": 1},
        )

    def action_open_exit_page_report(self):
        self.ensure_one()
        return self._scoped_report_action(
            "matomo_analytics.matomo_page_metric_action",
            self.env._("Exit Pages"),
            extra=[("metric_type", "=", "exit")],
            search_defaults={"filter_exit": 1},
        )

    def action_open_conversion_report(self):
        self.ensure_one()
        return self._scoped_report_action(
            "matomo_analytics.matomo_goal_metric_action",
            self.env._("Goal Reporting"),
            search_defaults={"group_by_goal": 1},
        )

    def _scoped_report_action(
        self,
        action_xmlid,
        title,
        date_from=None,
        date_to=None,
        extra=None,
        search_defaults=None,
    ):
        self.ensure_one()
        action = self.env.ref(action_xmlid).read()[0]
        action["name"] = "%s (%s)" % (
            title,
            self.selected_range_label or self.env._("Current range"),
        )
        action["domain"] = self._metric_domain(
            date_from or self.date_from,
            date_to or self.date_to,
            extra=extra,
        )
        context = action.get("context") or {}
        if not isinstance(context, dict):
            context = {}
        context["search_default_instance_id"] = self.instance_id.id
        for key, value in (search_defaults or {}).items():
            context["search_default_%s" % key] = value
        action["context"] = context
        return action

    def _metric_domain(self, date_from, date_to, extra=None):
        self.ensure_one()
        domain = [
            ("instance_id", "=", self.instance_id.id),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ]
        if extra:
            domain.extend(extra)
        return domain

    def _delta_percent(self, current_value, compare_value):
        if not compare_value:
            return 0.0
        return ((current_value - compare_value) / compare_value) * 100.0

    def _weighted_bounce_rate(self, metrics):
        total_sessions = sum(metrics.mapped("sessions"))
        if not total_sessions:
            return 0.0
        return sum(
            metric.sessions * metric.bounce_rate for metric in metrics if metric.sessions
        ) / total_sessions

    def _conversion_rate(self, conversions, sessions):
        if not sessions:
            return 0.0
        return (conversions / sessions) * 100.0

    def _build_sync_status_summary(self, current_daily_metrics=None):
        self.ensure_one()
        if not self.instance_id:
            return ""
        if not self.latest_sync_log_id:
            return self.env._(
                "No sync log is available yet. Run Sync Now before relying on these reports."
            )

        messages = []
        if self.last_sync_state == "success":
            messages.append(
                self.env._(
                    "Last sync succeeded. Insights use stored Odoo analytics for this connection."
                )
            )
        elif self.last_sync_state == "partial":
            summary = self.env._(
                "Last sync imported partial data. Review the latest sync log before interpreting missing sections."
            )
            if self.last_sync_warning_count:
                summary = "%s %s" % (
                    summary,
                    self.env._("Warnings: %s.") % self.last_sync_warning_count,
                )
            messages.append(summary)
        elif self.last_sync_state == "failed":
            messages.append(
                self.env._(
                    "Last sync failed. These insights only reflect the most recently stored data."
                )
            )
        else:
            messages.append(
                self.env._(
                    "No completed sync has been recorded yet for this connection."
                )
            )

        current_daily_metrics = current_daily_metrics or self.env["matomo.daily.metric"]
        if current_daily_metrics and self.latest_available_date:
            if self.latest_available_date < self.date_to:
                messages.append(
                    self.env._(
                        "Stored data is stale for the selected period. Latest stored day: %s."
                    )
                    % self.latest_available_date
                )
        elif self.date_from and self.date_to:
            messages.append(
                self.env._(
                    "No stored daily metrics were found for the selected period."
                )
            )
        return " ".join(messages)

    def _build_data_quality_summary(
        self,
        current_daily_metrics,
        compare_date_from=False,
        compare_date_to=False,
    ):
        self.ensure_one()
        current_summary = self._coverage_summary(
            current_daily_metrics,
            self.date_from,
            self.date_to,
            self.env._("current period"),
        )
        if not compare_date_from or not compare_date_to:
            return current_summary
        compare_metrics = self.env["matomo.daily.metric"].search(
            self._metric_domain(compare_date_from, compare_date_to)
        )
        compare_summary = self._coverage_summary(
            compare_metrics,
            compare_date_from,
            compare_date_to,
            self.env._("comparison period"),
        )
        return "%s %s" % (current_summary, compare_summary)

    def _coverage_summary(self, metrics, date_from, date_to, label):
        expected_days = self._period_day_count(date_from, date_to)
        available_days = len(metrics)
        if not metrics:
            return self.env._(
                "No stored data covers the %s from %s to %s."
            ) % (label, date_from, date_to)
        if available_days >= expected_days:
            return self.env._(
                "Stored data covers all %s days in the %s."
            ) % (expected_days, label)
        return self.env._(
            "Stored data covers %s of %s days in the %s."
        ) % (available_days, expected_days, label)

    def _comparison_range(self):
        self.ensure_one()
        if not self.comparison_enabled or not self.date_from or not self.date_to:
            return False, False
        if (
            self.comparison_mode == "custom"
            and self.compare_date_from
            and self.compare_date_to
        ):
            return self.compare_date_from, self.compare_date_to
        return self._previous_period_range(self.date_from, self.date_to)

    def _previous_period_range(self, date_from, date_to):
        days = self._period_day_count(date_from, date_to)
        return date_from - timedelta(days=days), date_from - timedelta(days=1)

    def _period_day_count(self, date_from, date_to):
        if not date_from or not date_to:
            return 0
        return (date_to - date_from).days + 1

    def _apply_date_range_preset(self):
        self.ensure_one()
        days = PRESET_DAY_MAPPING.get(self.date_range_preset)
        if not days:
            return
        today = fields.Date.context_today(self)
        self.date_to = today
        self.date_from = today - timedelta(days=days - 1)

    def _matching_date_range_preset(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if not self.date_from or not self.date_to or self.date_to != today:
            return "custom"
        day_count = self._period_day_count(self.date_from, self.date_to)
        for preset, days in PRESET_DAY_MAPPING.items():
            if day_count == days:
                return preset
        return "custom"

    def _format_range_label(self, date_from, date_to, preset="custom"):
        self.ensure_one()
        preset_label_map = dict(self._fields["date_range_preset"].selection)
        if preset == "previous_period":
            prefix = self.env._("Previous period")
        else:
            prefix = preset_label_map.get(preset)
        if prefix and prefix != preset_label_map.get("custom"):
            return "%s (%s - %s)" % (prefix, date_from, date_to)
        return "%s - %s" % (date_from, date_to)

    def _build_change_summary(self):
        self.ensure_one()
        if not self.comparison_enabled or not self.compare_range_label:
            return self.env._(
                "Enable a comparison period to see what changed versus the previous range."
            )

        insights = [
            self._describe_percent_change(
                self.sessions_delta,
                self.env._("Traffic"),
                self.env._("sessions"),
            ),
            self._describe_percent_change(
                self.conversions_delta,
                self.env._("Conversions"),
                self.env._("goal completions"),
            ),
            self._describe_point_change(
                self.bounce_rate_delta,
                self.env._("Bounce rate"),
                negative_is_good=True,
            ),
            self._describe_point_change(
                self.conversion_rate_delta,
                self.env._("Conversion rate"),
                negative_is_good=False,
            ),
        ]
        return " ".join([insight for insight in insights if insight])

    def _build_next_step_summary(self):
        self.ensure_one()
        if self.total_sessions == 0:
            return self.env._(
                "Start with sync health and date coverage because no stored traffic is available for this scope."
            )
        if self.conversions_delta < 0:
            return self.env._(
                "Investigate goals and landing pages first because conversions are trailing the comparison period."
            )
        if self.sessions_delta < 0:
            return self.env._(
                "Investigate channels, referrers, and countries first because traffic is down."
            )
        if self.bounce_rate_delta > 0:
            return self.env._(
                "Investigate landing and exit pages first because bounce rate worsened."
            )
        return self.env._(
            "Investigate top channels and goals next to confirm which sources and outcomes are sustaining growth."
        )

    def _describe_percent_change(self, delta, subject, metric_label):
        if not delta:
            return self.env._("%s is flat versus the comparison period.") % subject
        direction = self.env._("up") if delta > 0 else self.env._("down")
        return self.env._("%s is %s %.1f%% in %s.") % (
            subject,
            direction,
            abs(delta),
            metric_label,
        )

    def _describe_point_change(self, delta, subject, negative_is_good=False):
        if not delta:
            return self.env._("%s is unchanged.") % subject
        improved = delta < 0 if negative_is_good else delta > 0
        direction = self.env._("improved") if improved else self.env._("worsened")
        return self.env._("%s %s by %.2f points.") % (
            subject,
            direction,
            abs(delta),
        )

    def _build_channel_summary(self, records):
        rows = self._aggregate_rows(
            records,
            key_getter=lambda record: record.channel_name or self.env._("Unknown"),
            init_values=lambda record, key: {"label": key},
            update=lambda values, record: values.update(
                {
                    "sessions": values.get("sessions", 0) + (record.sessions or 0),
                    "visitors": values.get("visitors", 0) + (record.visitors or 0),
                    "conversions": values.get("conversions", 0.0)
                    + (record.conversions or 0.0),
                }
            ),
            sort_key=lambda values: (values.get("sessions", 0), values.get("conversions", 0.0)),
            limit=5,
        )
        summary = self._format_ranked_summary(
            rows,
            lambda row: self.env._(
                "%s: %s sessions, %s visitors, %s conversions"
            )
            % (
                row["label"],
                row.get("sessions", 0),
                row.get("visitors", 0),
                row.get("conversions", 0.0),
            ),
            empty_message=self.env._(
                "No stored channel records are available for this period."
            ),
        )
        top_channel = rows[0]["label"] if rows else ""
        return summary, top_channel

    def _build_country_summary(self, records):
        rows = self._aggregate_rows(
            records,
            key_getter=lambda record: record.country_name or self.env._("Unknown"),
            init_values=lambda record, key: {"label": key},
            update=lambda values, record: values.update(
                {
                    "sessions": values.get("sessions", 0) + (record.sessions or 0),
                    "visitors": values.get("visitors", 0) + (record.visitors or 0),
                    "conversions": values.get("conversions", 0.0)
                    + (record.conversions or 0.0),
                }
            ),
            sort_key=lambda values: (values.get("sessions", 0), values.get("conversions", 0.0)),
            limit=5,
        )
        return self._format_ranked_summary(
            rows,
            lambda row: self.env._("%s: %s sessions, %s conversions")
            % (row["label"], row.get("sessions", 0), row.get("conversions", 0.0)),
            empty_message=self.env._(
                "No stored country records are available for this period."
            ),
        )

    def _build_referrer_summary(self, records):
        rows = self._aggregate_rows(
            records,
            key_getter=lambda record: (
                record.referrer_name or self.env._("Unknown"),
                record.referrer_type or "",
            ),
            init_values=lambda record, key: {
                "label": key[0],
                "referrer_type": key[1],
            },
            update=lambda values, record: values.update(
                {
                    "sessions": values.get("sessions", 0) + (record.sessions or 0),
                    "conversions": values.get("conversions", 0.0)
                    + (record.conversions or 0.0),
                }
            ),
            sort_key=lambda values: (values.get("sessions", 0), values.get("conversions", 0.0)),
            limit=5,
        )
        return self._format_ranked_summary(
            rows,
            lambda row: self.env._("%s%s: %s sessions, %s conversions")
            % (
                row["label"],
                " (%s)" % row["referrer_type"] if row.get("referrer_type") else "",
                row.get("sessions", 0),
                row.get("conversions", 0.0),
            ),
            empty_message=self.env._(
                "No stored referrer records are available for this period."
            ),
        )

    def _build_page_summary(self, records, metric_type):
        if metric_type == "landing":
            primary_metric = "entrances"
            secondary_metric = "bounce_rate"
            secondary_label = self.env._("bounce")
            empty_message = self.env._(
                "No stored landing-page records are available for this period."
            )
        elif metric_type == "exit":
            primary_metric = "exits"
            secondary_metric = "exit_rate"
            secondary_label = self.env._("exit")
            empty_message = self.env._(
                "No stored exit-page records are available for this period."
            )
        else:
            primary_metric = "visits"
            secondary_metric = "pageviews"
            secondary_label = self.env._("pageviews")
            empty_message = self.env._(
                "No stored page records are available for this period."
            )
        rows = self._aggregate_rows(
            records,
            key_getter=lambda record: (
                record.page_url or record.page_label or self.env._("Unknown"),
                record.page_label or record.page_url or self.env._("Unknown"),
            ),
            init_values=lambda record, key: {"url": key[0], "label": key[1]},
            update=lambda values, record: values.update(
                {
                    "visits": values.get("visits", 0) + (record.visits or 0),
                    "pageviews": values.get("pageviews", 0) + (record.pageviews or 0),
                    "entrances": values.get("entrances", 0) + (record.entrances or 0),
                    "exits": values.get("exits", 0) + (record.exits or 0),
                    "bounce_weighted_sum": values.get("bounce_weighted_sum", 0.0)
                    + (record.bounce_rate or 0.0) * (record.visits or 0),
                    "bounce_weight": values.get("bounce_weight", 0)
                    + (record.visits or 0),
                    "exit_weighted_sum": values.get("exit_weighted_sum", 0.0)
                    + (record.exit_rate or 0.0) * (record.exits or 0),
                    "exit_weight": values.get("exit_weight", 0) + (record.exits or 0),
                }
            ),
            sort_key=lambda values: (values.get(primary_metric, 0), values.get("visits", 0)),
            limit=5,
        )
        for row in rows:
            row["bounce_rate"] = (
                row["bounce_weighted_sum"] / row["bounce_weight"]
                if row.get("bounce_weight")
                else 0.0
            )
            row["exit_rate"] = (
                row["exit_weighted_sum"] / row["exit_weight"]
                if row.get("exit_weight")
                else 0.0
            )
        return self._format_ranked_summary(
            rows,
            lambda row: self._format_page_summary_line(
                row,
                primary_metric,
                secondary_metric,
                secondary_label,
            ),
            empty_message=empty_message,
        )

    def _format_page_summary_line(
        self,
        row,
        primary_metric,
        secondary_metric,
        secondary_label,
    ):
        if secondary_metric in ("bounce_rate", "exit_rate"):
            secondary_value = self.env._("%.1f%% %s") % (
                row.get(secondary_metric, 0.0),
                secondary_label,
            )
        else:
            secondary_value = self.env._("%s %s") % (
                row.get(secondary_metric, 0),
                secondary_label,
            )
        return self.env._("%s: %s %s, %s") % (
            row.get("label"),
            row.get(primary_metric, 0),
            primary_metric,
            secondary_value,
        )

    def _build_goal_summary(self, records):
        rows = self._aggregate_rows(
            records,
            key_getter=lambda record: record.goal_name or self.env._("Goal"),
            init_values=lambda record, key: {"label": key},
            update=lambda values, record: values.update(
                {
                    "conversions": values.get("conversions", 0.0)
                    + (record.conversions or 0.0),
                    "revenue": values.get("revenue", 0.0) + (record.revenue or 0.0),
                }
            ),
            sort_key=lambda values: (values.get("conversions", 0.0), values.get("revenue", 0.0)),
            limit=5,
        )
        return self._format_ranked_summary(
            rows,
            lambda row: self.env._("%s: %s conversions, revenue %s")
            % (
                row["label"],
                row.get("conversions", 0.0),
                row.get("revenue", 0.0),
            ),
            empty_message=self.env._(
                "No stored goal records are available for this period."
            ),
        )

    def _aggregate_rows(
        self,
        records,
        key_getter,
        init_values,
        update,
        sort_key,
        limit=5,
    ):
        aggregates = {}
        for record in records:
            key = key_getter(record)
            if key not in aggregates:
                aggregates[key] = init_values(record, key)
            update(aggregates[key], record)
        rows = list(aggregates.values())
        rows.sort(key=sort_key, reverse=True)
        return rows[:limit]

    def _format_ranked_summary(self, rows, formatter, empty_message):
        if not rows:
            return empty_message
        return "\n".join(
            [
                "%s. %s" % (index, formatter(row))
                for index, row in enumerate(rows, start=1)
            ]
        )
