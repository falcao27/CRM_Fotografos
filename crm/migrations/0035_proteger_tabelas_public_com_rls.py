from django.db import migrations


def proteger_tabelas_public(apps, schema_editor):
    """
    Impede que as tabelas criadas pelo Django sejam acessadas pela Data API.

    A aplicacao usa uma conexao PostgreSQL direta no backend, normalmente com o
    papel `postgres` (dono das tabelas), que nao e limitado por RLS. Nao usamos
    FORCE ROW LEVEL SECURITY para preservar esse comportamento.
    """
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            DO $$
            DECLARE
                tabela record;
            BEGIN
                FOR tabela IN
                    SELECT n.nspname AS esquema, c.relname AS nome
                    FROM pg_class AS c
                    JOIN pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relkind IN ('r', 'p')
                LOOP
                    EXECUTE format(
                        'ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',
                        tabela.esquema,
                        tabela.nome
                    );
                    EXECUTE format(
                        'REVOKE ALL PRIVILEGES ON TABLE %I.%I FROM anon, authenticated',
                        tabela.esquema,
                        tabela.nome
                    );
                END LOOP;
            END
            $$;
            """
        )
        cursor.execute(
            """
            REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public
            FROM anon, authenticated;

            ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
            REVOKE ALL PRIVILEGES ON TABLES FROM anon, authenticated;

            ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
            REVOKE ALL PRIVILEGES ON SEQUENCES FROM anon, authenticated;
            """
        )


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0034_evento_valor_recebido_cartao"),
    ]

    operations = [
        migrations.RunPython(
            proteger_tabelas_public,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
