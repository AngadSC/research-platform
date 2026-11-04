from django.db import migrations

# D23: reject UPDATE, DELETE and TRUNCATE on the audit table. Postgres only (D15).
CREATE = """
CREATE FUNCTION audit_auditevent_reject() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditevent is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_auditevent_no_change BEFORE UPDATE OR DELETE ON audit_auditevent
    FOR EACH ROW EXECUTE FUNCTION audit_auditevent_reject();
CREATE TRIGGER audit_auditevent_no_truncate BEFORE TRUNCATE ON audit_auditevent
    FOR EACH STATEMENT EXECUTE FUNCTION audit_auditevent_reject();
"""
DROP = """
DROP TRIGGER audit_auditevent_no_truncate ON audit_auditevent;
DROP TRIGGER audit_auditevent_no_change ON audit_auditevent;
DROP FUNCTION audit_auditevent_reject();
"""


def run(sql):
    def forward(apps, schema_editor):
        if schema_editor.connection.vendor == "postgresql":
            schema_editor.execute(sql)

    return forward


class Migration(migrations.Migration):
    dependencies = [("audit", "0002_initial")]
    operations = [migrations.RunPython(run(CREATE), run(DROP))]
