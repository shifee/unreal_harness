# Unreal Harness Command Reference (UE 5.8)

`Content/Python/execute_actions.py` and its `ACTION_HANDLERS` mapping are authoritative. Use `system.describe_actions` for runtime discovery. Public fields use `snake_case`; Unreal virtual paths begin with `/Game` unless an engine asset is explicitly accepted.

## Document contract

```json
{
  "format_version": "1.0",
  "dry_run": false,
  "commands": [
    {"id": "unique_id", "action": "system.capabilities", "depends_on": [], "arguments": {}}
  ]
}
```

The executor validates the complete document before making changes. IDs must be unique, dependencies must reference earlier commands, and the limit is 200 commands. With `dry_run: true`, the result contains a validated plan and performs no commands.

Every result uses a stable audit envelope:

```json
{
  "format_version": "1.0",
  "harness_version": "0.1.0",
  "run_id": "uuid",
  "success": true,
  "commands": [
    {
      "id": "unique_id",
      "action": "content.create_folder",
      "success": true,
      "data": {},
      "changed_objects": ["/Game/AI"]
    }
  ],
  "errors": [],
  "changed_objects": ["/Game/AI"]
}
```

Failed commands preserve the readable `error` field and add a stable `error_code`. Entries in the top-level `errors` array contain `command_id`, `code`, `message`, and a traceback for diagnostics. `changed_objects` is present on every executed command and at the top level; inspect it before retrying a failed mutating batch.

## `system.capabilities`

Returns harness and engine versions, supported actions, graph-bridge availability, and graph node kinds.

```json
{"id":"capabilities","action":"system.capabilities","arguments":{}}
```

## `system.describe_actions`

Returns the action catalog and whether each action mutates editor state.

```json
{"id":"describe","action":"system.describe_actions","arguments":{}}
```

## `content.create_folder`

```json
{"id":"folder","action":"content.create_folder","arguments":{"path":"/Game/AI"}}
```

## `content.list`

Lists asset paths with bounded output. Arguments: `path` (default `/Game`), `recursive`, `query`, and `limit` (1–2000).

```json
{"id":"list","action":"content.list","arguments":{"path":"/Game/AI","recursive":true,"query":"BP_","limit":200}}
```

## `asset.inspect`

```json
{"id":"asset","action":"asset.inspect","arguments":{"asset":"/Game/AI/BP_Test.BP_Test"}}
```

## `material.create`

Creates a simple Material with Base Color, Metallic, and Roughness expressions. Existing assets are never replaced.

```json
{"id":"iron","action":"material.create","arguments":{"folder":"/Game/AI/Materials","name":"M_Iron","base_color":[0.16,0.18,0.21,1.0],"metallic":1.0,"roughness":0.3}}
```

## `material.inspect`

Returns class, parent, expression count, and discoverable scalar/vector/static-switch parameters.

```json
{"id":"inspect_material","action":"material.inspect","arguments":{"material":"/Game/AI/Materials/M_Iron.M_Iron"}}
```

## `material_instance.create`

```json
{"id":"instance","action":"material_instance.create","arguments":{"folder":"/Game/AI/Materials","name":"MI_IronDark","parent":"/Game/AI/Materials/M_Iron.M_Iron"}}
```

## `material_instance.set_parameters`

Parameter maps are optional. Parameter names must exist in the parent material.

```json
{"id":"params","action":"material_instance.set_parameters","arguments":{"material_instance":"/Game/AI/Materials/MI_IronDark.MI_IronDark","scalar":{"Roughness":0.4},"vector":{"Tint":[0.1,0.12,0.15,1.0]},"static_switch":{"UseDetail":true}}}
```

## `blueprint.create`

Existing Blueprints are never replaced, even if `replace_existing` is supplied.

```json
{"id":"create_bp","action":"blueprint.create","arguments":{"folder":"/Game/AI/Blueprints","name":"BP_Test","parent_class":"/Script/Engine.Actor"}}
```

## `blueprint.inspect`

Returns parent/generated classes, graph names, components, transforms, meshes, and material slots.

```json
{"id":"inspect_bp","action":"blueprint.inspect","arguments":{"blueprint":"/Game/AI/Blueprints/BP_Test.BP_Test"}}
```

## `blueprint.compile`

```json
{"id":"compile","action":"blueprint.compile","arguments":{"blueprint":"/Game/AI/Blueprints/BP_Test.BP_Test","save":false}}
```

## `blueprint.edit`

Operations: `add_component`, `set_component_property`, `set_component_material`, `set_component_transform`, and `set_class_property`.

```json
{
  "id":"edit_bp","action":"blueprint.edit","arguments":{
    "blueprint":"/Game/AI/Blueprints/BP_Test.BP_Test",
    "operations":[
      {"operation":"add_component","component_type":"/Script/Engine.StaticMeshComponent","component_name":"Body","attach_to":"DefaultSceneRoot"},
      {"operation":"set_component_property","component_name":"Body","property":"static_mesh","value":"/Engine/BasicShapes/Sphere.Sphere"},
      {"operation":"set_component_material","component_name":"Body","slot":0,"material":"/Game/AI/Materials/M_Iron.M_Iron"},
      {"operation":"set_component_transform","component_name":"Body","location":[0,0,50],"rotation":[0,0,0],"scale":[1,1,1]}
    ],"compile":true,"save":false
  }
}
```

## `blueprint.graph.inspect`

Returns node GUIDs, classes, titles, positions, pins, defaults, types, and links.

```json
{"id":"graph","action":"blueprint.graph.inspect","arguments":{"blueprint":"/Game/AI/Blueprints/BP_Test.BP_Test","graph":"EventGraph"}}
```

## `blueprint.graph.add_node`

Supported `node.kind` values are reported by `system.capabilities`: `function_call`, `event`, `branch`, `sequence`, `reroute`, `self`, `variable_get`, `variable_set`, and `dynamic_cast`. `node_id` is a document-local alias usable by later graph commands.

```json
{"id":"add_branch","action":"blueprint.graph.add_node","arguments":{"blueprint":"/Game/AI/Blueprints/BP_Test.BP_Test","graph":"EventGraph","node_id":"branch","node":{"kind":"branch"},"position":[300,0]}}
```

Kind-specific fields:

- `function_call` and `event`: `owner_class`, `function`.
- `variable_get` and `variable_set`: `variable_name` (the variable must already exist).
- `dynamic_cast`: `target_class`.

## `blueprint.graph.connect`

Unreal's K2 schema validates compatibility and may insert conversions. Pin matching ignores case, spaces, and underscores.

```json
{"id":"wire","action":"blueprint.graph.connect","arguments":{"blueprint":"/Game/AI/Blueprints/BP_Test.BP_Test","graph":"EventGraph","from":{"node":"begin_play","pin":"then"},"to":{"node":"branch","pin":"execute"}}}
```

## `blueprint.graph.set_pin_value`

Values are passed as strings to Unreal's graph schema.

```json
{"id":"condition","action":"blueprint.graph.set_pin_value","arguments":{"blueprint":"/Game/AI/Blueprints/BP_Test.BP_Test","graph":"EventGraph","node":"branch","pin":"condition","value":"true"}}
```

## `level.inspect`

Arguments: `query`, exact `class`, `selected_only`, and `limit` (1–5000).

```json
{"id":"level","action":"level.inspect","arguments":{"query":"Enemy","limit":200}}
```

## `level.spawn_actor`

Blueprint generated-class paths end in `_C`. Loading a non-current level is intentional and should be explicit.

```json
{"id":"spawn","action":"level.spawn_actor","arguments":{"level":"current","class":"/Game/AI/Blueprints/BP_Test.BP_Test_C","actor_label":"Test Actor","transform":{"location":[0,0,100],"rotation":[0,0,0],"scale":[1,1,1]}}}
```

## `level.set_actor_transform`

Identify exactly one actor by `actor_name` or `actor_label`. Omitted transform fields retain their current values.

```json
{"id":"move","action":"level.set_actor_transform","arguments":{"actor_label":"Test Actor","transform":{"location":[100,200,100]}}}
```

## `level.set_actor_property`

Sets one reflected editor property on exactly one actor.

```json
{"id":"tag","action":"level.set_actor_property","arguments":{"actor_label":"Test Actor","property":"tags","value":["Codex"]}}
```

## `project.save`

Mutating commands participate in editor Undo transactions. Persistence is explicit through this action unless a command's own `save` option is enabled.

```json
{"id":"save","action":"project.save","depends_on":["spawn"],"arguments":{"save_level":true,"save_assets":true}}
```

## Deliberate exclusions

The harness does not expose arbitrary Python, shell execution, asset deletion, Blueprint replacement, or bulk destructive operations. UE 5.8's native Unreal MCP can be enabled alongside the harness for interactive tool discovery, but the JSON executor remains the deterministic batch and audit layer.
