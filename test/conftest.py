import datetime
import json
from unittest.mock import Mock

import pytest
import pytz
from flask import g

from config import settings
from lib.security import sign_token
from lib.util_datetime import timedelta_months
from monstagpt.app import create_app
from monstagpt.blueprints.billing.gateways.stripecom import Card as PaymentCard
from monstagpt.blueprints.billing.gateways.stripecom import (
    Charge as PaymentCharge,
)
from monstagpt.blueprints.billing.gateways.stripecom import (
    Coupon as PaymentCoupon,
)
from monstagpt.blueprints.billing.gateways.stripecom import (
    Customer as PaymentCustomer,
)
from monstagpt.blueprints.billing.gateways.stripecom import (
    Event as PaymentEvent,
)
from monstagpt.blueprints.billing.gateways.stripecom import (
    Invoice as PaymentInvoice,
)
from monstagpt.blueprints.billing.gateways.stripecom import (
    Product as PaymentProduct,
)
from monstagpt.blueprints.billing.gateways.stripecom import (
    Subscription as PaymentSubscription,
)
from monstagpt.blueprints.billing.models.coupon import Coupon
from monstagpt.blueprints.billing.models.credit_card import CreditCard
from monstagpt.blueprints.billing.models.subscription import Subscription
from monstagpt.blueprints.user.models import User
from monstagpt.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    """
    Setup our flask test app, this only gets executed once.

    :return: Flask app
    """
    db_uri = settings.SQLALCHEMY_DATABASE_URI

    if "?" in db_uri:
        db_uri = db_uri.replace("?", "_test?")
    else:
        db_uri = f"{db_uri}_test"

    params = {
        "DEBUG": False,
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": db_uri,
    }

    _app = create_app(settings_override=params)

    # Establish an application context before running the tests.
    ctx = _app.app_context()
    ctx.push()

    yield _app

    ctx.pop()


@pytest.fixture(autouse=True)
def unset_user_session():
    g.pop("_login_user", None)


@pytest.fixture(scope="function")
def client(app):
    """
    Setup a test client, this gets executed for each test function.

    :param app: Pytest fixture
    :return: Flask test client
    """
    yield app.test_client()


@pytest.fixture(scope="session")
def db(app):
    """
    Setup our database, this only gets executed once per session.

    :param app: Pytest fixture
    :return: SQLAlchemy database session
    """
    _db.drop_all()
    _db.create_all()

    # Create a single user because a lot of tests do not mutate this user.
    # It will result in faster tests.
    params = {
        "role": "admin",
        "email": "admin@local.host",
        "password": "password",
        "coins": 100,
    }

    admin = User(**params)

    _db.session.add(admin)
    _db.session.commit()

    return _db


@pytest.fixture(scope="function")
def session(db):
    """
    Allow very fast tests by using rollbacks and nested sessions. This does
    require that your database supports SQL savepoints, and Postgres does.

    Read more about this at:
    http://stackoverflow.com/a/26624146

    :param db: Pytest fixture
    :return: None
    """
    db.session.begin_nested()

    yield db.session

    db.session.rollback()


@pytest.fixture(scope="session")
def token(db):
    """
    Serialize a token.

    :param db: Pytest fixture
    :return: Token
    """
    user = User.find_by_identity("admin@local.host")
    return sign_token(user.email)


@pytest.fixture(scope="function")
def users(db):
    """
    Create user fixtures. They reset per test.

    :param db: Pytest fixture
    :return: SQLAlchemy database session
    """
    db.session.query(User).delete()

    users = [
        {"role": "admin", "email": "admin@local.host", "password": "password"},
        {
            "active": False,
            "email": "disabled@local.host",
            "password": "password",
        },
    ]

    for user in users:
        db.session.add(User(**user))

    db.session.commit()

    return db


@pytest.fixture(scope="function")
def credit_cards(db):
    """
    Create credit card fixtures.

    :param db: Pytest fixture
    :return: SQLAlchemy database session
    """
    db.session.query(CreditCard).delete()

    may_29_2015 = datetime.date(2015, 5, 29)
    june_29_2015 = datetime.datetime(2015, 6, 29, 0, 0, 0)
    june_29_2015 = pytz.utc.localize(june_29_2015)

    credit_cards = [
        {
            "user_id": 1,
            "brand": "Visa",
            "last4": 4242,
            "exp_date": june_29_2015,
        },
        {
            "user_id": 1,
            "brand": "Visa",
            "last4": 4242,
            "exp_date": timedelta_months(12, may_29_2015),
        },
    ]

    for card in credit_cards:
        db.session.add(CreditCard(**card))

    db.session.commit()

    return db


@pytest.fixture(scope="function")
def coupons(db):
    """
    Create coupon fixtures.

    :param db: Pytest fixture
    :return: SQLAlchemy database session
    """
    db.session.query(Coupon).delete()

    may_29_2015 = datetime.datetime(2015, 5, 29, 0, 0, 0)
    may_29_2015 = pytz.utc.localize(may_29_2015)

    june_29_2015 = datetime.datetime(2015, 6, 29)
    june_29_2015 = pytz.utc.localize(june_29_2015)

    coupons = [
        {"amount_off": 1, "redeem_by": may_29_2015},
        {"amount_off": 1, "redeem_by": june_29_2015},
        {"percent_off": 0.33},
    ]

    for coupon in coupons:
        db.session.add(Coupon(**coupon))

    db.session.commit()

    return db


@pytest.fixture(scope="function")
def subscriptions(db):
    """
    Create subscription fixtures.

    :param db: Pytest fixture
    :return: SQLAlchemy database session
    """
    subscriber = User.find_by_identity("subscriber@local.host")
    if subscriber:
        subscriber.delete()
    db.session.query(Subscription).delete()

    params = {
        "role": "admin",
        "email": "subscriber@local.host",
        "name": "Subby",
        "password": "password",
        "customer_id": "cus_000",
    }

    subscriber = User(**params)

    # The account needs to be commit before we can assign a subscription to it.
    db.session.add(subscriber)
    db.session.commit()

    # Create a subscription.
    params = {"user_id": subscriber.id, "plan": "gold"}
    subscription = Subscription(**params)
    db.session.add(subscription)

    # Create a credit card.
    params = {
        "user_id": subscriber.id,
        "brand": "Visa",
        "last4": "4242",
        "exp_date": datetime.date(2015, 6, 1),
    }
    credit_card = CreditCard(**params)
    db.session.add(credit_card)

    db.session.commit()

    return db


@pytest.fixture(scope="session")
def mock_stripe():
    """
    Mock all of the Stripe API calls.

    :return:
    """
    PaymentCoupon.create = Mock(return_value={})
    PaymentCoupon.delete = Mock(return_value={})
    PaymentEvent.retrieve = Mock(return_value={})
    PaymentCard.update = Mock(return_value={})
    PaymentSubscription.create = Mock(return_value={})
    PaymentSubscription.update = Mock(return_value={})
    PaymentSubscription.cancel = Mock(return_value={})

    # Convert a JSON string into Python attributes.
    #   Source: http://stackoverflow.com/a/25318577
    class AtoD(dict):
        def __init__(self, *args, **kwargs):
            super(AtoD, self).__init__(*args, **kwargs)
            self.__dict__ = self

    customer_api = """{
        "id": "cus_000",
        "sources": {
            "data": [
              {
                "brand": "Visa",
                "exp_month": 6,
                "exp_year": 2023,
                "last4": "4242"
              }
            ]
        }
    }"""
    PaymentCustomer.create = Mock(
        return_value=json.loads(customer_api, object_hook=AtoD)
    )

    product_api = {
        "id": "prod_000",
        "type": "service",
        "name": "gold",
        "statement_descriptor": "GOLD MONTHLY",
    }
    PaymentProduct.retrieve = Mock(return_value=product_api)

    upcoming_invoice_api = {
        "created": 1433018770,
        "id": "in_000",
        "period_start": 1433018770,
        "period_end": 1433018770,
        "lines": {
            "data": [
                {
                    "id": "sub_000",
                    "object": "line_item",
                    "type": "subscription",
                    "livemode": True,
                    "amount": 0,
                    "currency": "usd",
                    "proration": False,
                    "period": {"start": 1433161742, "end": 1434371342},
                    "subscription": None,
                    "quantity": 1,
                    "plan": {
                        "interval": "month",
                        "name": "Gold",
                        "created": 1424879591,
                        "amount": 500,
                        "currency": "usd",
                        "id": "gold",
                        "object": "plan",
                        "livemode": False,
                        "interval_count": 1,
                        "trial_period_days": 14,
                        "metadata": {},
                        "nickname": "Gold",
                        "product": "prod_000",
                    },
                    "description": None,
                    "discountable": True,
                    "metadata": {},
                }
            ],
            "total_count": 1,
            "object": "list",
            "url": "/v1/invoices/in_000/lines",
        },
        "subtotal": 0,
        "total": 0,
        "customer": "cus_000",
        "object": "invoice",
        "attempted": True,
        "closed": True,
        "forgiven": False,
        "paid": True,
        "livemode": False,
        "attempt_count": 0,
        "amount_due": 500,
        "currency": "usd",
        "starting_balance": 0,
        "ending_balance": 0,
        "next_payment_attempt": None,
        "webhooks_delivered_at": None,
        "charge": None,
        "discount": None,
        "application_fee": None,
        "subscription": "sub_000",
        "tax_percent": None,
        "tax": None,
        "metadata": {},
        "statement_descriptor": None,
        "description": None,
        "receipt_number": None,
    }
    PaymentInvoice.upcoming = Mock(return_value=upcoming_invoice_api)

    charge_create_api = {
        "id": "ch_000",
        "object": "charge",
        "amount": 825,
        "amount_refunded": 0,
        "application_fee": None,
        "balance_transaction": "txn_000",
        "captured": True,
        "created": 1461334393,
        "currency": "usd",
        "customer": "cus_000",
        "description": None,
        "destination": None,
        "dispute": None,
        "failure_code": None,
        "failure_message": None,
        "fraud_details": {},
        "invoice": None,
        "livemode": False,
        "metadata": {},
        "order": None,
        "paid": True,
        "receipt_email": None,
        "receipt_number": None,
        "refunded": False,
        "refunds": {
            "object": "list",
            "data": [],
            "has_more": False,
            "total_count": 0,
            "url": "/v1/charges/ch_000/refunds",
        },
        "shipping": None,
        "source": {
            "id": "card_000",
            "object": "card",
            "address_city": None,
            "address_country": None,
            "address_line1": None,
            "address_line1_check": None,
            "address_line2": None,
            "address_state": None,
            "address_zip": None,
            "address_zip_check": None,
            "brand": "Visa",
            "country": "US",
            "customer": "cus_000",
            "cvc_check": "pass",
            "dynamic_last4": None,
            "exp_month": 12,
            "exp_year": 2030,
            "funding": "credit",
            "last4": "4242",
            "metadata": {},
            "name": None,
            "tokenization_method": None,
        },
        "source_transfer": None,
        "statement_descriptor": "MONSTAGPT TOKENS",
        "status": "succeeded",
    }
    PaymentCharge.create = Mock(return_value=charge_create_api)
