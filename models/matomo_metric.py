from odoo import fields, models


class MatomoDailyMetric(models.Model):
    _name = "matomo.daily.metric"
    _description = "Matomo Daily Metric"
    _order = "date desc, id desc"
    _check_company_auto = True

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
    date = fields.Date(required=True, index=True)
    visitors = fields.Integer()
    sessions = fields.Integer()
    conversions = fields.Float()
    bounce_rate = fields.Float(help="Percentage value between 0 and 100.")
    avg_session_duration = fields.Float(help="Average session duration in seconds.")
    top_channel = fields.Char()

    _sql_constraints = [
        (
            "matomo_daily_metric_unique",
            "unique(instance_id, date)",
            "Matomo daily metrics must be unique per instance and date.",
        )
    ]


class MatomoChannelMetric(models.Model):
    _name = "matomo.channel.metric"
    _description = "Matomo Channel Metric"
    _order = "date desc, sessions desc, id desc"
    _check_company_auto = True

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
    date = fields.Date(required=True, index=True)
    channel_name = fields.Char(required=True, index=True)
    sessions = fields.Integer()
    visitors = fields.Integer()
    conversions = fields.Float()
    bounce_rate = fields.Float()


class MatomoCountryMetric(models.Model):
    _name = "matomo.country.metric"
    _description = "Matomo Country Metric"
    _order = "date desc, sessions desc, id desc"
    _check_company_auto = True

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
    date = fields.Date(required=True, index=True)
    country_code = fields.Char(index=True)
    country_name = fields.Char(required=True, index=True)
    visitors = fields.Integer()
    sessions = fields.Integer()
    conversions = fields.Float()
    bounce_rate = fields.Float()


class MatomoReferrerMetric(models.Model):
    _name = "matomo.referrer.metric"
    _description = "Matomo Referrer Metric"
    _order = "date desc, sessions desc, id desc"
    _check_company_auto = True

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
    date = fields.Date(required=True, index=True)
    referrer_name = fields.Char(required=True, index=True)
    referrer_type = fields.Char(index=True)
    visitors = fields.Integer()
    sessions = fields.Integer()
    conversions = fields.Float()


class MatomoPageMetric(models.Model):
    _name = "matomo.page.metric"
    _description = "Matomo Page Metric"
    _order = "date desc, visits desc, id desc"
    _check_company_auto = True

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
    date = fields.Date(required=True, index=True)
    metric_type = fields.Selection(
        [
            ("page", "Top Page"),
            ("landing", "Landing Page"),
            ("exit", "Exit Page"),
        ],
        required=True,
        index=True,
    )
    page_label = fields.Char(required=True, index=True)
    page_url = fields.Char(index=True)
    visitors = fields.Integer()
    visits = fields.Integer()
    pageviews = fields.Integer()
    entrances = fields.Integer()
    exits = fields.Integer()
    bounce_rate = fields.Float()
    exit_rate = fields.Float()
    avg_time_on_page = fields.Float(help="Average time on page in seconds.")


class MatomoGoalMetric(models.Model):
    _name = "matomo.goal.metric"
    _description = "Matomo Goal Metric"
    _order = "date desc, conversions desc, id desc"
    _check_company_auto = True

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
    date = fields.Date(required=True, index=True)
    goal_key = fields.Char(required=True, index=True)
    goal_name = fields.Char(required=True, index=True)
    conversions = fields.Float()
    conversion_rate = fields.Float()
    revenue = fields.Float()
