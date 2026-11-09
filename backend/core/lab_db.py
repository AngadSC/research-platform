"""Database-level lab consistency (ARCHITECTURE section 1, D31). Postgres only (D15).

Two migration operations, reusable by any app that adds lab-scoped models:

* `LabForeignKey(table, column, parent_table, on_delete)`: composite FK
  `(column, lab_id) -> parent(id, lab_id)`, creating `UNIQUE (id, lab_id)` on the parent if needed.
* `LabM2MTrigger(through_table, left, right, ...)`: a trigger on a through table that rejects rows
  whose two sides differ in lab_id (and in project when both sides give a project column).

Both check existing data first and raise with table, row ids and both lab ids on a mismatch.
`tests/test_lab_db_constraints.py` fails for any lab-to-lab FK or M2M that lacks one.
"""

from django.db.migrations.operations.base import Operation

ON_DELETE = {
    "CASCADE": "ON DELETE CASCADE",
    "PROTECT": "",
    "SET_NULL": "ON DELETE SET NULL ({col})",
}


def fk_name(table, column, scope="lab_id"):
    return f"{table}_{column}_{scope.removesuffix('_id')}_fk"[:63]


def unique_name(table, scope="lab_id"):
    return f"{table}_id_{scope.removesuffix('_id')}_uniq"[:63]


def trigger_name(table):
    return f"{table}_lab_chk"[:63]


def _mismatch_check(sql, label):
    """DO block that raises (listing the rows) when `sql` (cols: id, lab_a, lab_b) returns rows."""
    return f"""
DO $$
DECLARE bad text;
BEGIN
  SELECT string_agg(format('id=%s lab=%s vs %s', id, lab_a, lab_b), '; ') INTO bad
  FROM ({sql}) m;
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'lab mismatch in {label}: %', bad;
  END IF;
END $$;"""


class _PgOperation(Operation):
    reversible = True

    def state_forwards(self, app_label, state):
        pass

    def _run(self, schema_editor, sqls):
        if schema_editor.connection.vendor == "postgresql":
            for sql in sqls:
                schema_editor.execute(sql, params=None)  # '%' in plpgsql format()

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        self._run(schema_editor, self.forwards_sql())

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        self._run(schema_editor, self.backwards_sql())


class LabForeignKey(_PgOperation):
    """`scope` is the column both tables must agree on. `lab_id` by default; `project_id` keeps a
    child in the same project as its parent."""

    def __init__(self, table, column, parent_table, on_delete="PROTECT", scope="lab_id"):
        self.table, self.column, self.parent_table, self.on_delete, self.scope = (
            table,
            column,
            parent_table,
            on_delete,
            scope,
        )

    def forwards_sql(self):
        t, c, p, s = self.table, self.column, self.parent_table, self.scope
        uq = unique_name(p, s)
        action = ON_DELETE[self.on_delete].format(col=c)
        check = _mismatch_check(
            f'SELECT c.id, c."{s}" AS lab_a, p."{s}" AS lab_b FROM "{t}" c '
            f'JOIN "{p}" p ON p.id = c."{c}" WHERE c."{s}" <> p."{s}"',
            f"{t}.{c} -> {p}",
        )
        return [
            check,
            f"""
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{uq}') THEN
    ALTER TABLE "{p}" ADD CONSTRAINT "{uq}" UNIQUE (id, "{s}");
  END IF;
END $$;""",
            f'ALTER TABLE "{t}" ADD CONSTRAINT "{fk_name(t, c, s)}" FOREIGN KEY ("{c}", "{s}") '
            f'REFERENCES "{p}" (id, "{s}") {action} DEFERRABLE INITIALLY DEFERRED',
        ]

    def backwards_sql(self):
        # the parent's UNIQUE (id, scope) is left in place: other FKs may use it.
        name = fk_name(self.table, self.column, self.scope)
        return [f'ALTER TABLE "{self.table}" DROP CONSTRAINT "{name}"']


FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION core_m2m_same_lab() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE
  -- TG_ARGV: left table, left col, right table, right col, left project col, right project col
  cond text := 'l.lab_id = r.lab_id';
  ok boolean;
BEGIN
  IF TG_ARGV[4] <> '' AND TG_ARGV[5] <> '' THEN
    cond := cond || format(' AND l.%I IS NOT NULL AND l.%I IS NOT DISTINCT FROM r.%I',
                           TG_ARGV[4], TG_ARGV[4], TG_ARGV[5]);
  END IF;
  EXECUTE format('SELECT %s FROM %I l, %I r WHERE l.id = $1::uuid AND r.id = $2::uuid',
                 cond, TG_ARGV[0], TG_ARGV[2])
    INTO ok USING to_jsonb(NEW) ->> TG_ARGV[1], to_jsonb(NEW) ->> TG_ARGV[3];
  -- a missing row (ok IS NULL) is left to the FK constraints
  IF ok IS FALSE THEN
    RAISE EXCEPTION 'M2M link across labs or projects: %.% / %.%',
      TG_ARGV[0], to_jsonb(NEW) ->> TG_ARGV[1], TG_ARGV[2], to_jsonb(NEW) ->> TG_ARGV[3]
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $f$;"""


class LabM2MTrigger(_PgOperation):
    """`left` / `right` are (table, through_column); `*_project` is the table's project column
    ("id" for projects_project) or "" when the side has no project rule."""

    def __init__(self, through_table, left, right, left_project="", right_project=""):
        self.through_table, self.left, self.right = through_table, tuple(left), tuple(right)
        self.left_project, self.right_project = left_project, right_project

    def forwards_sql(self):
        (lt, lc), (rt, rc) = self.left, self.right
        t = self.through_table
        proj = ""
        if self.left_project and self.right_project:
            lp, rp = self.left_project, self.right_project
            proj = f' OR l."{lp}" IS NULL OR l."{lp}" IS DISTINCT FROM r."{rp}"'
        check = _mismatch_check(
            f'SELECT x.id, l.lab_id AS lab_a, r.lab_id AS lab_b FROM "{t}" x '
            f'JOIN "{lt}" l ON l.id = x."{lc}" JOIN "{rt}" r ON r.id = x."{rc}" '
            f"WHERE l.lab_id <> r.lab_id{proj}",
            t,
        )
        args = ", ".join(f"'{a}'" for a in (lt, lc, rt, rc, self.left_project, self.right_project))
        return [
            check,
            FUNCTION_SQL,
            f'CREATE TRIGGER "{trigger_name(t)}" BEFORE INSERT OR UPDATE ON "{t}" '
            f"FOR EACH ROW EXECUTE FUNCTION core_m2m_same_lab({args})",
        ]

    def backwards_sql(self):
        return [f'DROP TRIGGER "{trigger_name(self.through_table)}" ON "{self.through_table}"']
