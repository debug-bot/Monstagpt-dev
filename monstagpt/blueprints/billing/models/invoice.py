import datetime

from sqlalchemy import or_
from sqlalchemy import text

from config import settings
from lib.util_sqlalchemy import ResourceMixin
from monstagpt.blueprints.billing.gateways.stripecom import (
    Charge as PaymentCharge,
)
from monstagpt.blueprints.billing.gateways.stripecom import (
    Customer as PaymentCustomer,
)
from monstagpt.blueprints.billing.gateways.stripecom import (
    Invoice as PaymentInvoice,
)
from monstagpt.blueprints.billing.models.coupon import Coupon
from monstagpt.blueprints.billing.models.credit_card import CreditCard
from monstagpt.extensions import db


class Invoice(ResourceMixin, db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True)

    # Relationships.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user = db.relationship("User", viewonly=True)

    # Invoice details.
    plan = db.Column(db.String(128), index=True)
    receipt_number = db.Column(db.String(128), index=True)
    description = db.Column(db.String(128))
    period_start_on = db.Column(db.Date)
    period_end_on = db.Column(db.Date)
    currency = db.Column(db.String(8))
    tax = db.Column(db.Integer())
    tax_percent = db.Column(db.Float())
    total = db.Column(db.Integer())
    paid = db.Column(db.String(10))
    url = db.Column(db.String(250))

    # De-normalize the card details so we can render a user's history properly
    # even if they have no active subscription or changed cards at some point.
    brand = db.Column(db.String(32))
    last4 = db.Column(db.String(4))
    exp_date = db.Column(db.Date, index=True)

    def __init__(self, **kwargs):
        # Call Flask-SQLAlchemy's constructor.
        super(Invoice, self).__init__(**kwargs)

    @classmethod
    def search(cls, query):
        """
        Search a resource by 1 or more fields.

        :param query: Search query
        :type query: str
        :return: SQLAlchemy filter
        """
        from monstagpt.blueprints.user.models import User

        if query == "":
            return text("")

        search_query = "%{0}%".format(query)
        search_chain = (
            User.email.ilike(search_query),
            User.username.ilike(search_query),
        )

        return or_(*search_chain)

    @classmethod
    def parse_from_event(cls, payload):
        """
        Parse and return the invoice information that will get saved locally.

        :return: dict
        """
        data = payload["data"]["object"]
        plan_info = data["lines"]["data"][0]["plan"]

        period_start_on = datetime.datetime.utcfromtimestamp(
            data["lines"]["data"][0]["period"]["start"]
        ).date()
        period_end_on = datetime.datetime.utcfromtimestamp(
            data["lines"]["data"][0]["period"]["end"]
        ).date()

        description = ""
        for key, value in settings.STRIPE_PLANS.items():
            if value.get("id") == plan_info["id"]:
                description = value.get("statement_descriptor")

        invoice = {
            "customer_id": data["customer"],
            "plan": plan_info["nickname"],
            "receipt_number": data["receipt_number"],
            "description": description,
            "period_start_on": period_start_on,
            "period_end_on": period_end_on,
            "currency": data["currency"],
            "tax": data["tax"],
            # "tax_percent": data["tax_percent"],
            "total": data["total"],
        }

        return invoice

    @classmethod
    def parse_from_api(cls, invoice):
        """
        Parse and return the invoice information we are interested in.

        :param invoice: Stripe invoice result
        :type invoice: dict
        :return: dict
        """
        plan_info = invoice["lines"]["data"][0]["plan"]
        date = datetime.datetime.utcfromtimestamp(invoice["created"])

        description = ""
        for key, value in settings.STRIPE_PLANS.items():
            if value.get("id") == plan_info["id"]:
                description = value.get("statement_descriptor")

        invoice = {
            "plan": plan_info["nickname"],
            "description": description,
            "next_bill_on": date,
            "amount_due": invoice["amount_due"],
            "interval": plan_info["interval"],
        }

        return invoice

    @classmethod
    def prepare_and_save(cls, parsed_event):
        """
        Potentially save the invoice after argument the event fields.

        :param parsed_event: Event params to be saved
        :type parsed_event: dict
        :return: User instance
        """
        # Avoid circular imports.
        from monstagpt.blueprints.user.models import User

        # Only save the invoice if the user is valid at this point.
        id = parsed_event.get("customer_id")
        user = User.query.filter((User.customer_id == id)).first()

        if user and user.credit_card:
            parsed_event["user_id"] = user.id
            # parsed_event["brand"] = user.credit_card.brand
            # parsed_event["last4"] = user.credit_card.last4
            # parsed_event["exp_date"] = user.credit_card.exp_date

            del parsed_event["customer_id"]

            invoice = Invoice(**parsed_event)
            invoice.save()

        return user

    @classmethod
    def upcoming(cls, customer_id):
        """
        Return the upcoming invoice item.

        :param customer_id: Stripe customer id
        :type customer_id: int
        :return: Stripe invoice object
        """
        invoice = PaymentInvoice.upcoming(customer_id)

        return Invoice.parse_from_api(invoice)

    def create(
        self,
        user=None,
        currency=None,
        amount=None,
        coins=None,
        coupon=None,
        token=None,
    ):
        """
        Create an invoice item.

        :param user: User to apply the subscription to
        :type user: User instance
        :param amount: Stripe currency
        :type amount: str
        :param amount: Amount in cents
        :type amount: int
        :param coins: Amount of coins
        :type coins: int
        :param coupon: Coupon code to apply
        :type coupon: str
        :param token: Token returned by JavaScript
        :type token: str
        :return: bool
        """
        if token is None:
            return False

        customer = PaymentCustomer.create(token=token, email=user.email)

        if coupon:
            self.coupon = coupon.upper()
            coupon = Coupon.query.filter(Coupon.code == self.coupon).first()
            amount = coupon.apply_discount_to(amount)

        charge = PaymentCharge.create(customer.id, currency, amount)

        # Redeem the coupon.
        if coupon:
            coupon.redeem()

        # Add the coins to the user.
        user.add_bought_coins(coins)

        period_on = datetime.datetime.utcfromtimestamp(charge.get("created"))
        card_params = CreditCard.extract_card_params(customer)

        self.user_id = user.id
        self.plan = "&mdash;"
        self.receipt_number = charge.get("receipt_number")
        self.description = charge.get("statement_descriptor")
        self.period_start_on = period_on
        self.period_end_on = period_on
        self.currency = charge.get("currency")
        self.tax = None
        self.tax_percent = None
        self.total = charge.get("amount")
        self.brand = card_params.get("brand")
        self.last4 = card_params.get("last4")
        self.exp_date = card_params.get("exp_date")

        db.session.add(self)
        db.session.add(user)
        db.session.commit()

        return True
