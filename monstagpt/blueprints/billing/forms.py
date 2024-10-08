from flask_babel import lazy_gettext as _
from flask_wtf import FlaskForm
from wtforms import HiddenField
from wtforms import SelectField
from wtforms import StringField
from wtforms.validators import DataRequired
from wtforms.validators import Length
from wtforms.validators import Optional

from config.settings import COIN_BUNDLES


def choices_from_coin_bundles():
    """
    Convert the COIN_BUNDLE settings into select box items.

    :return: list
    """
    choices = []

    for bundle in COIN_BUNDLES:
        pair = (str(bundle.get("coins")), bundle.get("label"))
        choices.append(pair)

    return choices


class SubscriptionForm(FlaskForm):
    stripe_key = HiddenField(
        _("Stripe publishable key"), [DataRequired(), Length(1, 254)]
    )
    plan = HiddenField(_("Plan"), [DataRequired(), Length(1, 254)])
    coupon_code = StringField(
        _("Do you have a coupon code?"), [Optional(), Length(1, 128)]
    )
    name = StringField(_("Name on card"), [DataRequired(), Length(1, 254)])


class UpdateSubscriptionForm(FlaskForm):
    coupon_code = StringField(
        _("Do you have a coupon code?"), [Optional(), Length(1, 254)]
    )


class CancelSubscriptionForm(FlaskForm):
    pass


class PaymentForm(FlaskForm):
    stripe_key = HiddenField(
        _("Stripe publishable key"), [DataRequired(), Length(1, 254)]
    )
    coin_bundles = SelectField(
        _("How many tokens do you want?"),
        [DataRequired()],
        choices=choices_from_coin_bundles(),
    )
    coupon_code = StringField(
        _("Do you have a coupon code?"), [Optional(), Length(1, 128)]
    )
    name = StringField(_("Name on card"), [DataRequired(), Length(1, 254)])
