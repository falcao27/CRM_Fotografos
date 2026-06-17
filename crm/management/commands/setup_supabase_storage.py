from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from crm.storage.supabase import criar_bucket_supabase


class Command(BaseCommand):
    help = "Cria o bucket publico no Supabase Storage para uploads do CRM."

    def handle(self, *args, **options):
        if not settings.SUPABASE_URL or not settings.SUPABASE_SECRET_KEY:
            raise CommandError("Configure SUPABASE_URL e SUPABASE_SECRET_KEY no .env antes de continuar.")

        status, body = criar_bucket_supabase()
        if status in (200, 201):
            self.stdout.write(self.style.SUCCESS(f"Bucket '{settings.SUPABASE_STORAGE_BUCKET}' criado com sucesso."))
            return

        if status == 400 and "already exists" in body.lower():
            self.stdout.write(self.style.WARNING(f"Bucket '{settings.SUPABASE_STORAGE_BUCKET}' ja existe."))
            return

        raise CommandError(f"Falha ao criar bucket (HTTP {status}): {body}")
