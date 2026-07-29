-- Execute este arquivo no SQL Editor de CADA projeto Supabase mencionado no
-- alerta. Ele mostra quais tabelas estavam desprotegidas e aplica a mesma
-- protecao da migration Django 0035.
--
-- O CRM usa conexao PostgreSQL direta no backend. Por isso nao sao criadas
-- politicas para anon/authenticated e nao e usado FORCE ROW LEVEL SECURITY.

-- 1. Auditoria antes da correcao (salve o resultado).
select
    n.nspname as esquema,
    c.relname as tabela,
    c.relrowsecurity as rls_habilitada,
    has_table_privilege('anon', c.oid, 'SELECT') as anon_pode_ler,
    has_table_privilege('anon', c.oid, 'INSERT,UPDATE,DELETE') as anon_pode_alterar,
    has_table_privilege('authenticated', c.oid, 'SELECT') as autenticado_pode_ler
from pg_class as c
join pg_namespace as n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind in ('r', 'p')
order by c.relname;

-- Remove uma versao anterior da automacao, caso o script tenha sido executado
-- parcialmente.
drop event trigger if exists crm_garantir_rls;
drop function if exists public.crm_habilitar_rls_em_novas_tabelas();

-- 2. Protege todas as tabelas public existentes.
do $$
declare
    tabela record;
begin
    for tabela in
        select n.nspname as esquema, c.relname as nome
        from pg_class as c
        join pg_namespace as n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relkind in ('r', 'p')
    loop
        execute format(
            'alter table %I.%I enable row level security',
            tabela.esquema,
            tabela.nome
        );
        execute format(
            'revoke all privileges on table %I.%I from anon, authenticated',
            tabela.esquema,
            tabela.nome
        );
    end loop;
end
$$;

revoke all privileges on all sequences in schema public
from anon, authenticated;

alter default privileges for role postgres in schema public
revoke all privileges on tables from anon, authenticated;

alter default privileges for role postgres in schema public
revoke all privileges on sequences from anon, authenticated;

-- 3. Validacao: esta consulta deve retornar zero linhas.
select
    n.nspname as esquema,
    c.relname as tabela
from pg_class as c
join pg_namespace as n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind in ('r', 'p')
  and (
      not c.relrowsecurity
      or has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE')
      or has_table_privilege(
          'authenticated',
          c.oid,
          'SELECT,INSERT,UPDATE,DELETE'
      )
  )
order by c.relname;
