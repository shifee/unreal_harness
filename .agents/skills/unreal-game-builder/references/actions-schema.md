# Unreal Harness Command Schema

`Content/Python/execute_actions.py` and its `ACTION_HANDLERS` mapping are the source of truth. This reference documents the actions distributed with this release.

## Document format

```json
{
  "format_version": "1.0",
  "commands": []
}
```

Every command needs a unique `id`, a supported `action`, and an `arguments` object. Optional `depends_on` is an array of earlier command IDs; a command is skipped when any dependency failed.

## `content.create_folder`

```json
{
  "id": "create_folder",
  "action": "content.create_folder",
  "arguments": {"path": "/Game/AI/Blueprints"}
}
```

The path must begin with `/Game` and cannot contain `..`.

## `blueprint.create`

```json
{
  "id": "create_blueprint",
  "action": "blueprint.create",
  "arguments": {
    "folder": "/Game/AI/Blueprints",
    "name": "BP_TestActor",
    "parent_class": "/Script/Engine.Actor",
    "replace_existing": false
  }
}
```

Existing Blueprints are never replaced automatically, including when `replace_existing` is true.

## `blueprint.edit`

Supported operations are `add_component`, `set_component_property`, `set_component_transform`, and `set_class_property`.

```json
{
  "id": "edit_blueprint",
  "action": "blueprint.edit",
  "arguments": {
    "blueprint": "/Game/AI/Blueprints/BP_TestActor.BP_TestActor",
    "operations": [
      {
        "operation": "add_component",
        "component_type": "/Script/Engine.StaticMeshComponent",
        "component_name": "CubeMesh",
        "attach_to": "DefaultSceneRoot"
      },
      {
        "operation": "set_component_property",
        "component_name": "CubeMesh",
        "property": "static_mesh",
        "value": "/Engine/BasicShapes/Cube.Cube"
      },
      {
        "operation": "set_component_transform",
        "component_name": "CubeMesh",
        "location": [0.0, 0.0, 50.0],
        "rotation": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0]
      },
      {
        "operation": "set_class_property",
        "property": "can_be_damaged",
        "value": true
      }
    ],
    "compile": true,
    "save": true
  }
}
```

Rotation order is `[pitch, yaw, roll]`. Asset-valued component properties currently recognized by the executor are `static_mesh`, `skeletal_mesh`, `material`, and `child_actor_class`.

## `level.spawn_actor`

Generated Blueprint class paths must end in `_C`.

```json
{
  "id": "spawn_actor",
  "action": "level.spawn_actor",
  "arguments": {
    "level": "current",
    "class": "/Game/AI/Blueprints/BP_TestActor.BP_TestActor_C",
    "actor_label": "Test Actor",
    "transform": {
      "location": [0.0, 0.0, 100.0],
      "rotation": [0.0, 0.0, 0.0],
      "scale": [1.0, 1.0, 1.0]
    }
  }
}
```

Use a `/Game` level path instead of `current` only when loading that level is intended.

## `project.save`

```json
{
  "id": "save_project",
  "action": "project.save",
  "depends_on": ["spawn_actor"],
  "arguments": {"save_level": true, "save_assets": true}
}
```

## Unsupported operations

The distributed executor does not support `level.inspect`, Blueprint variables, Event Graph nodes, Blueprint functions, deletion, replacement, arbitrary Python, or arbitrary shell commands.
