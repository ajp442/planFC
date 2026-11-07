import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Print a new VAPID key pair for Web Push, as lines to paste into .env."

    def handle(self, *args, **options):
        private_key = ec.generate_private_key(ec.SECP256R1())
        # The browser's applicationServerKey: the uncompressed P-256 point.
        public = private_key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        # pywebpush reads the raw 32-byte private value, base64url-encoded.
        private = private_key.private_numbers().private_value.to_bytes(32, "big")

        self.stdout.write(f"VAPID_PUBLIC_KEY={b64url(public)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={b64url(private)}")
        self.stderr.write(
            "Set these once and keep them: changing the pair silently breaks every "
            "existing subscription, and members must turn notifications on again."
        )
