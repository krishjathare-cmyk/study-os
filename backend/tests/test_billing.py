import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.billing import create_checkout_url, process_webhook
from app.database import Base


class FakeSignatureError(Exception):
    pass


class BillingTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = models.User(
            full_name="Subscriber",
            email="subscriber@example.com",
            hashed_password="hash",
            account_type="student",
            email_verified=True,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.environment = patch.dict(
            os.environ,
            {
                "STRIPE_SECRET_KEY": "sk_test_example",
                "STRIPE_WEBHOOK_SECRET": "whsec_example",
                "STRIPE_PRICE_STUDENT_PRO": "price_student",
                "STRIPE_PRICE_PROFESSIONAL": "price_professional",
                "FRONTEND_URL": "https://study.example.com",
            },
        )
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.db.close()

    def test_checkout_uses_server_selected_price_and_user_metadata(self):
        create = Mock(return_value=SimpleNamespace(url="https://checkout.stripe.test/session"))
        fake_stripe = SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace(create=create)))

        with patch("app.billing._stripe", return_value=fake_stripe):
            url = create_checkout_url(self.db, self.user, "student_pro")

        self.assertEqual("https://checkout.stripe.test/session", url)
        parameters = create.call_args.kwargs
        self.assertEqual("subscription", parameters["mode"])
        self.assertEqual("price_student", parameters["line_items"][0]["price"])
        self.assertEqual(str(self.user.id), parameters["metadata"]["user_id"])

    def test_signed_subscription_webhook_activates_and_revokes_features(self):
        events = [
            {
                "id": "evt_active",
                "created": 100,
                "type": "customer.subscription.updated",
                "data": {
                    "object": {
                        "id": "sub_123",
                        "customer": "cus_123",
                        "status": "active",
                        "metadata": {
                            "user_id": str(self.user.id),
                            "plan": "student_pro",
                        },
                        "items": {"data": [{"price": {"id": "price_student"}}]},
                    }
                },
            },
            {
                "id": "evt_cancelled",
                "created": 200,
                "type": "customer.subscription.deleted",
                "data": {
                    "object": {
                        "id": "sub_123",
                        "customer": "cus_123",
                        "status": "canceled",
                        "metadata": {
                            "user_id": str(self.user.id),
                            "plan": "student_pro",
                        },
                        "items": {"data": [{"price": {"id": "price_student"}}]},
                    }
                },
            },
        ]
        construct_event = Mock(side_effect=events)
        fake_stripe = SimpleNamespace(
            Webhook=SimpleNamespace(construct_event=construct_event),
            error=SimpleNamespace(SignatureVerificationError=FakeSignatureError),
        )

        with patch("app.billing._stripe", return_value=fake_stripe):
            process_webhook(self.db, b"{}", "signed")
            self.db.refresh(self.user)
            self.assertEqual("student_pro", self.user.subscription_plan)
            process_webhook(self.db, b"{}", "signed")

        self.db.refresh(self.user)
        self.assertEqual("free", self.user.subscription_plan)
        self.assertEqual(2, self.db.query(models.ProcessedWebhookEvent).count())


if __name__ == "__main__":
    unittest.main()
