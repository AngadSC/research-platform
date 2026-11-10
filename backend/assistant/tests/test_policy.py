"""Lab AI policy over MCP (D188): `off` is a 403 on the MCP endpoint, `mcp` and `full` work, and a
lab that turned AI off disappears from a connection that also names another lab."""

import json

import pytest

from assistant.tests.test_mcp import data, pat, rpc
from labs.models import AiPolicy

pytestmark = pytest.mark.django_db


def list_labs(token):
    r = rpc(token, "tools/call", {"name": "list_labs", "arguments": {}})
    return r, ([x["id"] for x in data(r)["labs"]] if r.status_code == 200 else None)


def test_mcp_is_403_when_the_only_granted_lab_turned_ai_off(world):
    token = pat(world.u.contrib, world.lab_a)
    assert list_labs(token)[0].status_code == 200
    world.lab_a.ai_policy = AiPolicy.OFF
    world.lab_a.save()
    for method, params in (
        ("tools/list", {}),
        ("tools/call", {"name": "list_labs", "arguments": {}}),
        ("ping", None),
    ):
        r = rpc(token, method, params)
        assert r.status_code == 403, method
        assert "turned off" in r.json()["error"]["message"]
    # turning it back on restores access with the same token
    world.lab_a.ai_policy = AiPolicy.FULL
    world.lab_a.save()
    assert list_labs(token)[0].status_code == 200


@pytest.mark.parametrize("policy", [AiPolicy.MCP, AiPolicy.FULL])
def test_mcp_works_when_the_policy_allows_it(world, policy):
    world.lab_a.ai_policy = policy
    world.lab_a.save()
    r, ids = list_labs(pat(world.u.contrib, world.lab_a))
    assert r.status_code == 200 and ids == [str(world.lab_a.pk)]


def test_an_off_lab_is_hidden_from_a_connection_that_names_two(world, make_user, join):
    user = make_user(display_name="Two")
    join(user, world.lab_a, "member")
    join(user, world.lab_b, "member")
    token = pat(user, world.lab_a, world.lab_b)
    assert sorted(list_labs(token)[1]) == sorted([str(world.lab_a.pk), str(world.lab_b.pk)])
    world.lab_b.ai_policy = AiPolicy.OFF
    world.lab_b.save()
    r, ids = list_labs(token)
    assert r.status_code == 200 and ids == [str(world.lab_a.pk)]
    # and a call that names the off lab is refused like any lab the connection cannot see
    r = rpc(
        token,
        "tools/call",
        {"name": "list_projects", "arguments": {"lab_id": str(world.lab_b.pk)}},
    )
    assert r.json()["result"]["isError"] is True
    assert "SECRET" not in json.dumps(r.json())


def test_a_removed_member_still_sees_no_lab_not_a_policy_error(world):
    token = pat(world.u.contrib, world.lab_a)
    world.lab_a.ai_policy = AiPolicy.FULL
    from labs.models import LabMembership

    LabMembership.objects.for_lab(world.lab_a).filter(user=world.u.contrib).delete()
    r, ids = list_labs(token)
    assert r.status_code == 200 and ids == []
