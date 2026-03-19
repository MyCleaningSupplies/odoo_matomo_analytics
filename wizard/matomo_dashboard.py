from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class MatomoAnalyticsDashboard(models.TransientModel):
    _name = "matomo.analytics.dashboard"
    _description = "Matomo Analytics Dashboard"

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
    date_from = fields.Date(required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(required=True, default=lambda self: fields.Date.context_today(self))
    comparison_enabled = fields.Boolean(string="Compare to another period")
    compare_date_from = fields.Date()
    compare_date_to = fields.Date()
    selected_range_label = fields.Char(compute="_compute_metrics")
    compare_range_label = fields.Char(compute="_compute_metrics")
    report_scope_summary = fields.Char(compute="_compute_metrics")
    comparison_scope_summary = fields.Char(compute="_compute_metrics")
    last_successful_sync_at = fields.Datetime(compute="_compute_metrics")
    last_sync_state = fields.Selection(
        [("success", "Success"), ("partial", "Partial"), ("failed", "Failed")],
        compute="_compute_metrics",
    )
    last_sync_message = fields.Text(compute="_compute_metrics")
    sync_status_summary = fields.Text(compute="_compute_metrics")
    latest_sync_log_id = fields.Many2one("matomo.sync.log", compute="_compute_metrics")
    last_sync_warning_count = fields.Integer(compute="_compute_metrics")
    last_sync_warning_summary = fields.Char(compute="_compute_metrics")
    total_visitors = fields.Integer(compute="_compute_metrics")
    total_sessions = fields.Integer(compute="_compute_metrics")
    total_conversions = fields.Float(compute="_compute_metrics")
    bounce_rate = fields.Float(compute="_compute_metrics")
    top_channel = fields.Char(compute="_compute_metrics")
    compare_visitors = fields.Integer(compute="_compute_metrics")
    compare_sessions = fields.Integer(compute="_compute_metrics")
    compare_conversions = fields.Float(compute="_compute_metrics")
    compare_bounce_rate = fields.Float(compute="_compute_metrics")
    visitors_delta = fields.Float(compute="_compute_metrics")
    sessions_delta = fields.Float(compute="_compute_metrics")
    conversions_delta = fields.Float(compute="_compute_metrics")

    @api.model
    def _default_instance(self):
        return self.env["matomo.instance"].search(
            [("company_id", "in", self.env.companies.ids), ("active", "=", True)],
            limit=1,
        )

    @api.model
    def _default_date_from(self):
        return fields.Date.context_today(self) - timedelta(days=29)

    @api.depends(
        "instance_id",
        "date_from",
        "date_to",
        "comparison_enabled",
        "compare_date_from",
        "compare_date_to",
    )
    def _compute_metrics(self):
        daily_metric_model = self.env["matomo.daily.metric"]
        channel_metric_model = self.env["matomo.channel.metric"]
        for wizard in self:
            wizard.selected_range_label = ""
            wizard.compare_range_label = ""
            wizard.report_scope_summary = ""
            wizard.comparison_scope_summary = ""
            wizard.last_successful_sync_at = wizard.instance_id.last_successful_sync_at
            wizard.last_sync_state = wizard.instance_id.last_sync_state
            wizard.last_sync_message = wizard.instance_id.last_sync_message
            wizard.latest_sync_log_id = wizard.instance_id.latest_sync_log_id
            wizard.last_sync_warning_count = wizard.instance_id.last_sync_warning_count
            wizard.last_sync_warning_summary = (
                wizard.instance_id.last_sync_warning_summary
            )
            wizard.sync_status_summary = wizard._build_sync_status_summary()
            wizard.total_visitors = 0
            wizard.total_sessions = 0
            wizard.total_conversions = 0
            wizard.bounce_rate = 0
            wizard.top_channel = ""
            wizard.compare_visitors = 0
            wizard.compare_sessions = 0
            wizard.compare_conversions = 0
            wizard.compare_bounce_rate = 0
            wizard.visitors_delta = 0
            wizard.sessions_delta = 0
            wizard.conversions_delta = 0
            if not wizard.instance_id or not wizard.date_from or not wizard.date_to:
                continue

            wizard.selected_range_label = "%s - %s" % (wizard.date_from, wizard.date_to)
            wizard.report_scope_summary = wizard.env._(
                "Showing stored analytics for %s from %s to %s."
            ) % (wizard.instance_id.name, wizard.date_from, wizard.date_to)
            current_domain = wizard._metric_domain(wizard.date_from, wizard.date_to)
            current_metrics = daily_metric_model.search(current_domain)
            wizard.total_visitors = int(sum(current_metrics.mapped("visitors")))
            wizard.total_sessions = int(sum(current_metrics.mapped("sessions")))
            wizard.total_conversions = sum(current_metrics.mapped("conversions"))
            wizard.bounce_rate = wizard._weighted_bounce_rate(current_metrics)
            channel_groups = channel_metric_model.read_group(
                current_domain,
                ["sessions:sum"],
                ["channel_name"],
                lazy=False,
            )
            if channel_groups:
                wizard.top_channel = max(
                    channel_groups, key=lambda group: group.get("sessions", 0)
                ).get("channel_name") or ""

            if (
                wizard.comparison_enabled
                and wizard.compare_date_from
                and wizard.compare_date_to
            ):
                wizard.compare_range_label = "%s - %s" % (
                    wizard.compare_date_from,
                    wizard.compare_date_to,
                )
                wizard.comparison_scope_summary = wizard.env._(
                    "Comparing against %s to %s."
                ) % (wizard.compare_date_from, wizard.compare_date_to)
                compare_domain = wizard._metric_domain(
                    wizard.compare_date_from, wizard.compare_date_to
                )
                compare_metrics = daily_metric_model.search(compare_domain)
                wizard.compare_visitors = int(sum(compare_metrics.mapped("visitors")))
                wizard.compare_sessions = int(sum(compare_metrics.mapped("sessions")))
                wizard.compare_conversions = sum(
                    compare_metrics.mapped("conversions")
                )
                wizard.compare_bounce_rate = wizard._weighted_bounce_rate(
                    compare_metrics
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

    def action_refresh(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(self.env._("The start date must be before the end date."))
        if self.comparison_enabled and self.compare_date_from and self.compare_date_to:
            if self.compare_date_from > self.compare_date_to:
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
        wizard = wizard or self.create({"instance_id": instance.id})
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Matomo Overview"),
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

    def action_open_content_report(self):
        self.ensure_one()
        return self._scoped_report_action(
            "matomo_analytics.matomo_page_metric_action",
            self.env._("Content Reporting"),
            self.date_from,
            self.date_to,
            extra=[("metric_type", "in", ["page", "landing", "exit"])],
            search_defaults={"group_by_metric_type": 1},
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

    def _build_sync_status_summary(self):
        self.ensure_one()
        if not self.instance_id:
            return ""
        if not self.latest_sync_log_id:
            return self.env._(
                "No sync log is available yet. Run Sync Now before relying on these reports."
            )
        if self.last_sync_state == "success":
            return self.env._(
                "Last sync succeeded. The dashboard reflects the latest stored Matomo data for this connection."
            )
        if self.last_sync_state == "partial":
            summary = self.env._(
                "Last sync imported partial data. Review the latest sync log before interpreting missing report sections."
            )
            if self.last_sync_warning_count:
                summary = "%s %s" % (
                    summary,
                    self.env._("Warnings: %s.") % self.last_sync_warning_count,
                )
            return summary
        if self.last_sync_state == "failed":
            return self.env._(
                "Last sync failed. These reports only reflect the most recently stored data."
            )
        return self.env._(
            "No completed sync has been recorded yet for this connection."
        )
