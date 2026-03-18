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
    last_successful_sync_at = fields.Datetime(compute="_compute_metrics")
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
            wizard.last_successful_sync_at = wizard.instance_id.last_successful_sync_at
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
            current_domain = wizard._metric_domain(wizard.date_from, wizard.date_to)
            current_metrics = daily_metric_model.search(current_domain)
            wizard.total_visitors = int(sum(current_metrics.mapped("visitors")))
            wizard.total_sessions = int(sum(current_metrics.mapped("sessions")))
            wizard.total_conversions = sum(current_metrics.mapped("conversions"))
            if current_metrics:
                wizard.bounce_rate = sum(current_metrics.mapped("bounce_rate")) / len(
                    current_metrics
                )
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
                compare_domain = wizard._metric_domain(
                    wizard.compare_date_from, wizard.compare_date_to
                )
                compare_metrics = daily_metric_model.search(compare_domain)
                wizard.compare_visitors = int(sum(compare_metrics.mapped("visitors")))
                wizard.compare_sessions = int(sum(compare_metrics.mapped("sessions")))
                wizard.compare_conversions = sum(
                    compare_metrics.mapped("conversions")
                )
                if compare_metrics:
                    wizard.compare_bounce_rate = sum(
                        compare_metrics.mapped("bounce_rate")
                    ) / len(compare_metrics)
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
        return self.action_open_dashboard(instance=self.instance_id, wizard=self)

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

    def action_open_traffic_report(self):
        self.ensure_one()
        action = self.env.ref("matomo_analytics.matomo_channel_metric_action").read()[0]
        action["domain"] = self._metric_domain(self.date_from, self.date_to)
        return action

    def action_open_content_report(self):
        self.ensure_one()
        action = self.env.ref("matomo_analytics.matomo_page_metric_action").read()[0]
        action["domain"] = self._metric_domain(
            self.date_from,
            self.date_to,
            extra=[("metric_type", "in", ["page", "landing", "exit"])],
        )
        return action

    def action_open_conversion_report(self):
        self.ensure_one()
        action = self.env.ref("matomo_analytics.matomo_goal_metric_action").read()[0]
        action["domain"] = self._metric_domain(self.date_from, self.date_to)
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
