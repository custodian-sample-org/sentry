# Generated by Django 2.2.28 on 2023-01-31 20:37

from django.db import migrations

from sentry.new_migrations.migrations import CheckedMigration


class Migration(CheckedMigration):
    # This flag is used to mark that a migration shouldn't be automatically run in production. For
    # the most part, this should only be used for operations where it's safe to run the migration
    # after your code has deployed. So this should not be used for most operations that alter the
    # schema of a table.
    # Here are some things that make sense to mark as dangerous:
    # - Large data migrations. Typically we want these to be run manually by ops so that they can
    #   be monitored and not block the deploy for a long period of time while they run.
    # - Adding indexes to large tables. Since this can take a long time, we'd generally prefer to
    #   have ops run this and not block the deploy. Note that while adding an index is a schema
    #   change, it's completely safe to run the operation after the code has deployed.
    is_dangerous = True

    dependencies = [
        ("sentry", "0417_backfill_groupedmessage_substatus"),
    ]

    operations = (
        [
            migrations.RunSQL(
                sql=line,
                reverse_sql="",
                hints={"tables": ["sentry_actor"]},
            )
            for line in """
ALTER TABLE "sentry_actor" DROP CONSTRAINT IF EXISTS "sentry_actor_team_id_6ca8eba5_fk_sentry_team_id";
ALTER TABLE "sentry_actor" DROP CONSTRAINT IF EXISTS "sentry_actor_team_id_6ca8eba5_uniq";
DROP INDEX CONCURRENTLY IF EXISTS "sentry_actor_team_id_6ca8eba5";
DROP INDEX CONCURRENTLY IF EXISTS "sentry_actor_team_id_6ca8eba5_uniq";

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "sentry_actor_team_id_6ca8eba5_uniq" ON "sentry_actor" ("team_id");
ALTER TABLE "sentry_actor" ADD CONSTRAINT "sentry_actor_team_id_6ca8eba5_fk_sentry_team_id" FOREIGN KEY ("team_id") REFERENCES "sentry_team" ("id") DEFERRABLE INITIALLY DEFERRED NOT VALID;
ALTER TABLE "sentry_actor" VALIDATE CONSTRAINT "sentry_actor_team_id_6ca8eba5_fk_sentry_team_id";

ALTER TABLE "sentry_actor" DROP CONSTRAINT IF EXISTS "sentry_actor_user_id_c832ff63_uniq";
DROP INDEX CONCURRENTLY IF EXISTS "sentry_actor_user_id_c832ff63";
DROP INDEX CONCURRENTLY IF EXISTS "sentry_actor_user_id_c832ff63_uniq";
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "sentry_actor_user_id_c832ff63_uniq" ON "sentry_actor" ("user_id");
        """.splitlines()
            if line.strip()
        ]
        + [
            migrations.RunSQL(
                sql="SELECT 1",
                reverse_sql="""
ALTER TABLE "sentry_actor" ADD CONSTRAINT "sentry_actor_team_id_6ca8eba5_uniq" UNIQUE USING INDEX "sentry_actor_team_id_6ca8eba5_uniq";
            """,
                hints={"tables": ["sentry_actor"]},
            ),
            migrations.RunSQL(
                sql="SELECT 1",
                reverse_sql="""
ALTER TABLE "sentry_actor" ADD CONSTRAINT "sentry_actor_user_id_c832ff63_uniq" UNIQUE USING INDEX "sentry_actor_user_id_c832ff63_uniq";
            """,
                hints={"tables": ["sentry_actor"]},
            ),
        ]
    )
