from testing.sim.workspace_seed import select_workspace_files


def test_selects_only_versioned_bootstrap_and_skills():
    files = [
        "EVI_WORKSPACE/AGENTS.md",
        "EVI_WORKSPACE/TOOLS.md",
        "EVI_WORKSPACE/HEARTBEAT.md",
        "EVI_WORKSPACE/skills/inbox-triage/SKILL.md",
        "EVI_WORKSPACE/skills/inbox-triage/notes.md",
        "EVI_WORKSPACE/USER.md",
        "EVI_WORKSPACE/MEMORY.md",
        "EVI_WORKSPACE/memory/2026-01-01.md",
        "agent/main.py",
    ]
    assert select_workspace_files(files) == [
        "AGENTS.md",
        "HEARTBEAT.md",
        "TOOLS.md",
        "skills/inbox-triage/SKILL.md",
    ]


def test_never_personal_even_nested():
    assert select_workspace_files(["EVI_WORKSPACE/USER.md", "EVI_WORKSPACE/skills/x/USER.md"]) == []
