import json
import os
import re
import traceback
import uuid
from datetime import datetime, timezone

import unreal


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIONS_FILE = os.path.join(SCRIPT_DIR, "actions.json")
RESULT_FILE = os.path.join(SCRIPT_DIR, "result.json")
HARNESS_VERSION = "0.1.0"
MAX_COMMANDS = 200
CURRENT_CHANGED_OBJECTS = []


class HarnessError(RuntimeError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def log(message):
    unreal.log("[AI EXECUTOR] " + str(message))


def log_error(message):
    unreal.log_error("[AI EXECUTOR] " + str(message))


def require(condition, message, code="validation_error"):
    if not condition:
        raise HarnessError(code, message)


def error_record(error, command_id=None, include_traceback=False):
    record = {
        "command_id": command_id,
        "code": getattr(error, "code", "execution_failed"),
        "message": str(error),
    }
    details = getattr(error, "details", None)
    if details:
        record["details"] = details
    if include_traceback:
        record["traceback"] = traceback.format_exc()
    return record


def mark_changed(*values):
    for value in values:
        if value is None:
            continue
        path = value if isinstance(value, str) else object_path(value)
        if path and path not in CURRENT_CHANGED_OBJECTS:
            CURRENT_CHANGED_OBJECTS.append(path)


def merge_changed(target, values):
    for value in values:
        if value not in target:
            target.append(value)


def validate_game_path(path):
    require(isinstance(path, str), "Path must be a string")
    require(path.startswith("/Game"), "Path must start with /Game")
    require(".." not in path, "Path cannot contain '..'")
    return path.rstrip("/")


def validate_name(name):
    require(isinstance(name, str), "Name must be a string")
    require(
        re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) is not None,
        "Invalid Unreal name: " + name,
    )
    return name


def asset_package_path(asset_path):
    return asset_path.split(".")[0]


def make_vector(values, default):
    values = values if values is not None else default
    require(
        isinstance(values, list) and len(values) == 3,
        "Vector must contain exactly three numbers",
    )
    return unreal.Vector(float(values[0]), float(values[1]), float(values[2]))


def make_rotator(values):
    values = values if values is not None else [0.0, 0.0, 0.0]
    require(
        isinstance(values, list) and len(values) == 3,
        "Rotation must contain [pitch, yaw, roll]",
    )
    return unreal.Rotator(
        pitch=float(values[0]), yaw=float(values[1]), roll=float(values[2])
    )


def make_linear_color(values, default):
    values = values if values is not None else default
    require(
        isinstance(values, list) and len(values) in (3, 4),
        "Color must contain [r, g, b] or [r, g, b, a]",
    )
    alpha = float(values[3]) if len(values) == 4 else 1.0
    return unreal.LinearColor(
        float(values[0]), float(values[1]), float(values[2]), alpha
    )


def load_unreal_class(class_path):
    require(isinstance(class_path, str), "Class path must be a string")
    unreal_class = unreal.load_class(None, class_path)
    require(unreal_class is not None, "Could not load Unreal class: " + class_path)
    return unreal_class


def load_json_file(path):
    require(os.path.isfile(path), "File not found: " + path)
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def save_json_file(path, data):
    temporary_path = path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(temporary_path, path)


def object_path(value):
    return value.get_path_name() if value is not None else None


def vector_values(value):
    return [float(value.x), float(value.y), float(value.z)]


def rotator_values(value):
    return [float(value.pitch), float(value.yaw), float(value.roll)]


def execute_create_folder(arguments):
    path = validate_game_path(arguments["path"])
    if unreal.EditorAssetLibrary.does_directory_exist(path):
        return {"created": False, "path": path, "message": "Directory already exists"}
    success = unreal.EditorAssetLibrary.make_directory(path)
    require(success, "Could not create directory: " + path)
    mark_changed(path)
    return {"created": True, "path": path}


def execute_list_content(arguments):
    path = validate_game_path(arguments.get("path", "/Game"))
    recursive = bool(arguments.get("recursive", True))
    limit = int(arguments.get("limit", 200))
    require(1 <= limit <= 2000, "limit must be between 1 and 2000")
    assets = unreal.EditorAssetLibrary.list_assets(path, recursive, False)
    query = str(arguments.get("query", "")).lower().strip()
    if query:
        assets = [asset for asset in assets if query in str(asset).lower()]
    total = len(assets)
    return {"path": path, "total": total, "truncated": total > limit, "assets": assets[:limit]}


def execute_inspect_asset(arguments):
    path = validate_game_path(asset_package_path(arguments["asset"]))
    asset = unreal.load_asset(path)
    require(asset is not None, "Asset not found: " + path)
    asset_data = unreal.EditorAssetLibrary.find_asset_data(path)
    return {
        "path": object_path(asset),
        "name": asset.get_name(),
        "class": asset.get_class().get_path_name(),
        "package": asset.get_outermost().get_path_name(),
        "asset_class": str(asset_data.asset_class_path) if asset_data else None,
    }


def execute_create_blueprint(arguments):
    folder = validate_game_path(arguments["folder"])
    name = validate_name(arguments["name"])
    asset_path = folder + "/" + name
    object_path = asset_path + "." + name

    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        if arguments.get("replace_existing", False):
            raise RuntimeError("Automatic replacement is disabled for safety: " + asset_path)
        raise RuntimeError("Blueprint already exists: " + asset_path)

    if not unreal.EditorAssetLibrary.does_directory_exist(folder):
        require(
            unreal.EditorAssetLibrary.make_directory(folder),
            "Could not create directory: " + folder,
        )

    parent_class = load_unreal_class(arguments["parent_class"])
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", parent_class)
    blueprint = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, None, factory
    )
    require(blueprint is not None, "Could not create Blueprint: " + asset_path)
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, False)
    mark_changed(blueprint)
    return {
        "asset_path": object_path,
        "generated_class_path": object_path + "_C",
    }


def execute_create_material(arguments):
    folder = validate_game_path(arguments["folder"])
    name = validate_name(arguments["name"])
    asset_path = folder + "/" + name
    object_path = asset_path + "." + name

    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        if arguments.get("replace_existing", False):
            raise RuntimeError("Automatic replacement is disabled for safety: " + asset_path)
        raise RuntimeError("Material already exists: " + asset_path)

    if not unreal.EditorAssetLibrary.does_directory_exist(folder):
        require(
            unreal.EditorAssetLibrary.make_directory(folder),
            "Could not create directory: " + folder,
        )

    base_color = make_linear_color(
        arguments.get("base_color"), [0.18, 0.20, 0.22, 1.0]
    )
    metallic = float(arguments.get("metallic", 0.0))
    roughness = float(arguments.get("roughness", 0.5))
    require(0.0 <= metallic <= 1.0, "metallic must be between 0 and 1")
    require(0.0 <= roughness <= 1.0, "roughness must be between 0 and 1")

    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.Material, unreal.MaterialFactoryNew()
    )
    require(material is not None, "Could not create Material: " + asset_path)

    base_expression = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant3Vector, -400, -120
    )
    require(base_expression is not None, "Could not create Base Color expression")
    base_expression.set_editor_property("constant", base_color)
    require(
        unreal.MaterialEditingLibrary.connect_material_property(
            base_expression, "", unreal.MaterialProperty.MP_BASE_COLOR
        ),
        "Could not connect Base Color",
    )

    metallic_expression = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant, -400, 40
    )
    require(metallic_expression is not None, "Could not create Metallic expression")
    metallic_expression.set_editor_property("r", metallic)
    require(
        unreal.MaterialEditingLibrary.connect_material_property(
            metallic_expression, "", unreal.MaterialProperty.MP_METALLIC
        ),
        "Could not connect Metallic",
    )

    roughness_expression = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant, -400, 180
    )
    require(roughness_expression is not None, "Could not create Roughness expression")
    roughness_expression.set_editor_property("r", roughness)
    require(
        unreal.MaterialEditingLibrary.connect_material_property(
            roughness_expression, "", unreal.MaterialProperty.MP_ROUGHNESS
        ),
        "Could not connect Roughness",
    )

    unreal.MaterialEditingLibrary.recompile_material(material)
    require(
        unreal.EditorAssetLibrary.save_loaded_asset(material, False),
        "Could not save Material: " + asset_path,
    )
    mark_changed(material)
    return {
        "asset_path": object_path,
        "base_color": [base_color.r, base_color.g, base_color.b, base_color.a],
        "metallic": metallic,
        "roughness": roughness,
    }


def execute_inspect_material(arguments):
    path = validate_game_path(asset_package_path(arguments["material"]))
    material = unreal.load_asset(path)
    require(material is not None, "Material not found: " + path)
    editing = unreal.MaterialEditingLibrary
    result = {
        "path": object_path(material),
        "class": material.get_class().get_path_name(),
        "scalar_parameters": [],
        "vector_parameters": [],
        "static_switch_parameters": [],
    }
    for parameter in editing.get_scalar_parameter_names(material):
        name = str(parameter)
        item = {"name": name}
        if isinstance(material, unreal.MaterialInstanceConstant):
            item["value"] = float(
                editing.get_material_instance_scalar_parameter_value(material, parameter)
            )
        result["scalar_parameters"].append(item)
    for parameter in editing.get_vector_parameter_names(material):
        name = str(parameter)
        item = {"name": name}
        if isinstance(material, unreal.MaterialInstanceConstant):
            color = editing.get_material_instance_vector_parameter_value(material, parameter)
            item["value"] = [color.r, color.g, color.b, color.a]
        result["vector_parameters"].append(item)
    for parameter in editing.get_static_switch_parameter_names(material):
        name = str(parameter)
        item = {"name": name}
        if isinstance(material, unreal.MaterialInstanceConstant):
            item["value"] = bool(
                editing.get_material_instance_static_switch_parameter_value(material, parameter)
            )
        result["static_switch_parameters"].append(item)
    if isinstance(material, unreal.MaterialInstanceConstant):
        result["parent"] = object_path(material.get_editor_property("parent"))
    elif isinstance(material, unreal.Material):
        result["expression_count"] = int(editing.get_num_material_expressions(material))
    return result


def execute_create_material_instance(arguments):
    folder = validate_game_path(arguments["folder"])
    name = validate_name(arguments["name"])
    parent_path = validate_game_path(asset_package_path(arguments["parent"]))
    asset_path = folder + "/" + name
    require(
        not unreal.EditorAssetLibrary.does_asset_exist(asset_path),
        "Material instance already exists: " + asset_path,
    )
    parent = unreal.load_asset(parent_path)
    require(parent is not None, "Parent material not found: " + parent_path)
    if not unreal.EditorAssetLibrary.does_directory_exist(folder):
        require(unreal.EditorAssetLibrary.make_directory(folder), "Could not create directory: " + folder)
    instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew()
    )
    require(instance is not None, "Could not create Material Instance: " + asset_path)
    unreal.MaterialEditingLibrary.set_material_instance_parent(instance, parent)
    unreal.EditorAssetLibrary.save_loaded_asset(instance, False)
    mark_changed(instance)
    return {"asset_path": object_path(instance), "parent": object_path(parent)}


def execute_set_material_instance_parameters(arguments):
    path = validate_game_path(asset_package_path(arguments["material_instance"]))
    instance = unreal.load_asset(path)
    require(
        isinstance(instance, unreal.MaterialInstanceConstant),
        "Material Instance Constant not found: " + path,
    )
    editing = unreal.MaterialEditingLibrary
    changed = {"scalar": [], "vector": [], "static_switch": []}
    for name, value in arguments.get("scalar", {}).items():
        require(
            editing.set_material_instance_scalar_parameter_value(instance, str(name), float(value)),
            "Scalar parameter not found: " + str(name),
        )
        changed["scalar"].append(str(name))
    for name, value in arguments.get("vector", {}).items():
        require(
            editing.set_material_instance_vector_parameter_value(
                instance, str(name), make_linear_color(value, [0.0, 0.0, 0.0, 1.0])
            ),
            "Vector parameter not found: " + str(name),
        )
        changed["vector"].append(str(name))
    for name, value in arguments.get("static_switch", {}).items():
        require(
            editing.set_material_instance_static_switch_parameter_value(instance, str(name), bool(value)),
            "Static switch parameter not found: " + str(name),
        )
        changed["static_switch"].append(str(name))
    unreal.EditorAssetLibrary.save_loaded_asset(instance, False)
    mark_changed(instance)
    changed["material_instance"] = object_path(instance)
    return changed


def get_blueprint_components(blueprint):
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = subsystem.k2_gather_subobject_data_for_blueprint(blueprint)
    require(len(handles) > 0, "Blueprint does not contain subobject data")
    library = unreal.SubobjectDataBlueprintFunctionLibrary
    components = {}
    component_handles = {}
    for handle in handles:
        try:
            data = library.get_data(handle)
            display_name = str(library.get_display_name(data))
            variable_name = str(library.get_variable_name(data))
            component = library.get_object_for_blueprint(data, blueprint)
            if component is not None:
                components[display_name] = component
                components[variable_name] = component
                components[component.get_name()] = component
            component_handles[display_name] = handle
            component_handles[variable_name] = handle
        except Exception:
            pass
    return subsystem, handles[0], components, component_handles


def execute_inspect_blueprint(arguments):
    blueprint_path = validate_game_path(asset_package_path(arguments["blueprint"]))
    blueprint = unreal.load_asset(blueprint_path)
    require(isinstance(blueprint, unreal.Blueprint), "Blueprint not found: " + blueprint_path)
    _, _, components, _ = get_blueprint_components(blueprint)
    unique_components = []
    seen = set()
    for component in components.values():
        identity = object_path(component)
        if identity in seen:
            continue
        seen.add(identity)
        item = {
            "name": component.get_name(),
            "class": component.get_class().get_path_name(),
        }
        if isinstance(component, unreal.SceneComponent):
            item["relative_location"] = vector_values(component.get_editor_property("relative_location"))
            item["relative_rotation"] = rotator_values(component.get_editor_property("relative_rotation"))
            item["relative_scale"] = vector_values(component.get_editor_property("relative_scale3d"))
        if isinstance(component, unreal.MeshComponent):
            item["materials"] = [
                object_path(component.get_material(slot))
                for slot in range(component.get_num_materials())
            ]
        if isinstance(component, unreal.StaticMeshComponent):
            item["static_mesh"] = object_path(component.get_editor_property("static_mesh"))
        unique_components.append(item)
    graphs = []
    parent_class = None
    generated_class = object_path(blueprint.generated_class())
    bridge = getattr(unreal, "UnrealCodexGraphLibrary", None)
    if bridge is not None:
        graph_data = parse_graph_result(bridge.list_graphs(object_path(blueprint)))
        graphs = graph_data["graphs"]
        parent_class = graph_data.get("parent_class")
        generated_class = graph_data.get("generated_class", generated_class)
    return {
        "path": object_path(blueprint),
        "parent_class": parent_class,
        "generated_class": generated_class,
        "components": unique_components,
        "graphs": graphs,
    }


def execute_compile_blueprint(arguments):
    blueprint_path = validate_game_path(asset_package_path(arguments["blueprint"]))
    blueprint = unreal.load_asset(blueprint_path)
    require(isinstance(blueprint, unreal.Blueprint), "Blueprint not found: " + blueprint_path)
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    if arguments.get("save", False):
        unreal.EditorAssetLibrary.save_loaded_asset(blueprint, False)
    mark_changed(blueprint)
    return {"blueprint": object_path(blueprint), "compiled": True, "saved": bool(arguments.get("save", False))}


def add_component(blueprint, subsystem, root_handle, components, component_handles, operation):
    component_name = validate_name(operation["component_name"])
    require(component_name not in components, "Component already exists: " + component_name)
    component_class = load_unreal_class(operation["component_type"])
    parent_handle = component_handles.get(operation.get("attach_to"), root_handle)
    params = unreal.AddNewSubobjectParams(
        parent_handle=parent_handle,
        new_class=component_class,
        blueprint_context=blueprint,
    )
    new_handle, fail_reason = subsystem.add_new_subobject(params)
    require(not str(fail_reason).strip(), "Could not add component: " + str(fail_reason))
    require(
        subsystem.rename_subobject(handle=new_handle, new_name=unreal.Text(component_name)),
        "Could not rename component to: " + component_name,
    )
    library = unreal.SubobjectDataBlueprintFunctionLibrary
    component = library.get_object_for_blueprint(library.get_data(new_handle), blueprint)
    require(component is not None, "Could not access created component: " + component_name)
    components[component_name] = component
    component_handles[component_name] = new_handle
    return {"operation": "add_component", "component": component_name}


def convert_property_value(property_name, value):
    asset_properties = {"static_mesh", "skeletal_mesh", "material", "child_actor_class"}
    if property_name in asset_properties and isinstance(value, str) and value.startswith("/"):
        asset = unreal.load_asset(value)
        require(asset is not None, "Could not load asset: " + value)
        return asset
    return value


def find_component(components, component_name):
    component = components.get(component_name)
    if component is not None:
        return component
    normalized = re.sub(r"[^a-z0-9]", "", str(component_name).lower())
    normalized = normalized.removesuffix("genvariable")
    matches = []
    for candidate_name, candidate in components.items():
        candidate_normalized = re.sub(r"[^a-z0-9]", "", str(candidate_name).lower())
        candidate_normalized = candidate_normalized.removesuffix("genvariable")
        if candidate_normalized == normalized and candidate not in matches:
            matches.append(candidate)
    require(
        len(matches) <= 1,
        "Component name is ambiguous: " + component_name,
    )
    return matches[0] if matches else None


def set_component_property(components, operation):
    component_name = operation["component_name"]
    component = find_component(components, component_name)
    require(component is not None, "Component not found: " + component_name)
    property_name = operation["property"]
    component.set_editor_property(
        property_name, convert_property_value(property_name, operation["value"])
    )
    return {
        "operation": "set_component_property",
        "component": component_name,
        "property": property_name,
    }


def set_component_material(components, operation):
    component_name = operation["component_name"]
    component = find_component(components, component_name)
    require(component is not None, "Component not found: " + component_name)
    slot = int(operation.get("slot", 0))
    require(slot >= 0, "Material slot must be zero or greater")
    material_path = operation["material"]
    material = unreal.load_asset(material_path)
    require(material is not None, "Could not load material: " + material_path)
    component.set_material(slot, material)
    return {
        "operation": "set_component_material",
        "component": component_name,
        "slot": slot,
        "material": material_path,
    }


def set_component_transform(components, operation):
    component_name = operation["component_name"]
    component = find_component(components, component_name)
    require(component is not None, "Component not found: " + component_name)
    component.set_editor_property(
        "relative_location", make_vector(operation.get("location"), [0.0, 0.0, 0.0])
    )
    component.set_editor_property("relative_rotation", make_rotator(operation.get("rotation")))
    component.set_editor_property(
        "relative_scale3d", make_vector(operation.get("scale"), [1.0, 1.0, 1.0])
    )
    return {"operation": "set_component_transform", "component": component_name}


def set_class_property(blueprint, operation):
    generated_class = blueprint.generated_class()
    require(generated_class is not None, "Blueprint does not have a generated class")
    property_name = operation["property"]
    unreal.get_default_object(generated_class).set_editor_property(
        property_name, operation["value"]
    )
    return {"operation": "set_class_property", "property": property_name}


def execute_edit_blueprint(arguments):
    blueprint_path = asset_package_path(arguments["blueprint"])
    blueprint = unreal.load_asset(blueprint_path)
    require(blueprint is not None, "Blueprint not found: " + blueprint_path)
    subsystem, root_handle, components, component_handles = get_blueprint_components(blueprint)
    operation_results = []

    for operation in arguments.get("operations", []):
        name = operation.get("operation")
        if name == "add_component":
            result = add_component(
                blueprint, subsystem, root_handle, components, component_handles, operation
            )
        elif name == "set_component_property":
            result = set_component_property(components, operation)
        elif name == "set_component_material":
            result = set_component_material(components, operation)
        elif name == "set_component_transform":
            result = set_component_transform(components, operation)
        elif name == "set_class_property":
            result = set_class_property(blueprint, operation)
        elif name == "add_variable":
            raise RuntimeError("add_variable is not implemented yet")
        else:
            raise RuntimeError("Unsupported Blueprint operation: " + str(name))
        operation_results.append(result)

    if arguments.get("compile", True):
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    if arguments.get("save", True):
        unreal.EditorAssetLibrary.save_loaded_asset(blueprint, False)
    mark_changed(blueprint)
    return {
        "blueprint": blueprint_path,
        "operations": operation_results,
        "compiled": arguments.get("compile", True),
        "saved": arguments.get("save", True),
    }


def execute_spawn_actor(arguments):
    level_path = arguments.get("level", "current")
    if level_path != "current":
        level_path = validate_game_path(level_path)
        loaded = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(level_path)
        require(loaded, "Could not load level: " + level_path)

    class_path = arguments["class"]
    actor_class = load_unreal_class(class_path)
    transform = arguments.get("transform", {})
    location = make_vector(transform.get("location"), [0.0, 0.0, 0.0])
    rotation = make_rotator(transform.get("rotation"))
    scale = make_vector(transform.get("scale"), [1.0, 1.0, 1.0])
    actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
        actor_class, location, rotation
    )
    require(actor is not None, "Could not spawn actor")
    actor.set_actor_scale3d(scale)
    actor.set_actor_label(
        arguments.get("actor_label", arguments.get("actor_name", actor.get_name()))
    )
    mark_changed(actor)
    return {
        "actor_name": actor.get_name(),
        "actor_label": actor.get_actor_label(),
        "class": class_path,
    }


def actor_record(actor):
    return {
        "name": actor.get_name(),
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_path_name(),
        "path": actor.get_path_name(),
        "location": vector_values(actor.get_actor_location()),
        "rotation": rotator_values(actor.get_actor_rotation()),
        "scale": vector_values(actor.get_actor_scale3d()),
        "hidden": bool(actor.is_hidden_ed()),
    }


def execute_inspect_level(arguments):
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    query = str(arguments.get("query", "")).lower().strip()
    class_path = arguments.get("class")
    selected_only = bool(arguments.get("selected_only", False))
    if selected_only:
        selected = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors()
        selected_paths = {actor.get_path_name() for actor in selected}
        actors = [actor for actor in actors if actor.get_path_name() in selected_paths]
    if query:
        actors = [
            actor for actor in actors
            if query in actor.get_name().lower() or query in actor.get_actor_label().lower()
        ]
    if class_path:
        actors = [actor for actor in actors if actor.get_class().get_path_name() == class_path]
    limit = int(arguments.get("limit", 500))
    require(1 <= limit <= 5000, "limit must be between 1 and 5000")
    total = len(actors)
    return {
        "total": total,
        "truncated": total > limit,
        "actors": [actor_record(actor) for actor in actors[:limit]],
    }


def find_level_actor(arguments):
    name = arguments.get("actor_name")
    label = arguments.get("actor_label")
    require(name or label, "Provide actor_name or actor_label")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    matches = [
        actor for actor in actors
        if (name and actor.get_name() == name) or (label and actor.get_actor_label() == label)
    ]
    require(matches, "Actor not found: " + str(name or label))
    require(len(matches) == 1, "Actor reference is ambiguous: " + str(name or label))
    return matches[0]


def execute_set_actor_transform(arguments):
    actor = find_level_actor(arguments)
    transform = arguments.get("transform", {})
    location = make_vector(transform.get("location"), vector_values(actor.get_actor_location()))
    rotation = make_rotator(transform.get("rotation", rotator_values(actor.get_actor_rotation())))
    scale = make_vector(transform.get("scale"), vector_values(actor.get_actor_scale3d()))
    actor.set_actor_location_and_rotation(location, rotation, False, False)
    actor.set_actor_scale3d(scale)
    mark_changed(actor)
    return actor_record(actor)


def execute_set_actor_property(arguments):
    actor = find_level_actor(arguments)
    property_name = validate_name(arguments["property"])
    actor.set_editor_property(property_name, arguments["value"])
    mark_changed(actor)
    return {"actor": actor.get_path_name(), "property": property_name}


def execute_save_project(arguments):
    if arguments.get("save_level", True):
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    if arguments.get("save_assets", True):
        unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    return {
        "level_saved": arguments.get("save_level", True),
        "assets_saved": arguments.get("save_assets", True),
    }


GRAPH_NODE_ALIASES = {}


def graph_bridge():
    bridge = getattr(unreal, "UnrealCodexGraphLibrary", None)
    require(
        bridge is not None,
        "UnrealCodexGraph plugin is not loaded. Install it, enable it, and restart Unreal Editor.",
    )
    return bridge


def parse_graph_result(raw_result):
    try:
        result = json.loads(str(raw_result))
    except (TypeError, ValueError) as error:
        raise RuntimeError("Invalid response from UnrealCodexGraph: " + str(error))
    require(isinstance(result, dict), "UnrealCodexGraph response must be an object")
    require(result.get("success") is True, result.get("error", "UnrealCodexGraph operation failed"))
    return result


def graph_alias_key(blueprint_path, graph_name, node_id):
    return (blueprint_path, graph_name, node_id)


def resolve_graph_node(blueprint_path, graph_name, node_reference):
    require(isinstance(node_reference, str) and node_reference, "Node reference must be a string")
    return GRAPH_NODE_ALIASES.get(
        graph_alias_key(blueprint_path, graph_name, node_reference),
        node_reference,
    )


def graph_position(arguments):
    position = arguments.get("position", [0.0, 0.0])
    require(isinstance(position, list) and len(position) == 2, "Position must contain [x, y]")
    return unreal.Vector2D(float(position[0]), float(position[1]))


def execute_system_capabilities(arguments):
    bridge = getattr(unreal, "UnrealCodexGraphLibrary", None)
    data = {
        "harness_version": HARNESS_VERSION,
        "engine_version": str(unreal.SystemLibrary.get_engine_version()),
        "graph_bridge_available": bridge is not None,
        "actions": sorted(ACTION_HANDLERS),
    }
    if bridge is not None:
        data["graph_bridge"] = parse_graph_result(bridge.get_capabilities())
    return data


def execute_describe_actions(arguments):
    return {
        "harness_version": HARNESS_VERSION,
        "actions": [
            {"name": name, "mutating": name in MUTATING_ACTIONS}
            for name in sorted(ACTION_HANDLERS)
        ],
        "document_options": {"dry_run": "Validate and return the execution plan without running commands"},
    }


def execute_graph_inspect(arguments):
    return parse_graph_result(
        graph_bridge().inspect_graph(arguments["blueprint"], arguments.get("graph", "EventGraph"))
    )


def execute_graph_add_node(arguments):
    blueprint_path = arguments["blueprint"]
    graph_name = arguments.get("graph", "EventGraph")
    node_id = arguments["node_id"]
    node = arguments["node"]
    kind = node.get("kind")
    position = graph_position(arguments)
    require(isinstance(kind, str) and kind, "node.kind must be a non-empty string")
    raw_result = graph_bridge().add_node(
        blueprint_path,
        graph_name,
        kind,
        json.dumps(node, ensure_ascii=False),
        position,
    )
    result = parse_graph_result(raw_result)
    GRAPH_NODE_ALIASES[graph_alias_key(blueprint_path, graph_name, node_id)] = result["node_guid"]
    mark_changed(blueprint_path)
    result["node_id"] = node_id
    return result


def execute_graph_connect(arguments):
    blueprint_path = arguments["blueprint"]
    graph_name = arguments.get("graph", "EventGraph")
    source = arguments["from"]
    target = arguments["to"]
    result = parse_graph_result(
        graph_bridge().connect_pins(
            blueprint_path,
            graph_name,
            resolve_graph_node(blueprint_path, graph_name, source["node"]),
            source["pin"],
            resolve_graph_node(blueprint_path, graph_name, target["node"]),
            target["pin"],
        )
    )
    mark_changed(blueprint_path)
    return result


def execute_graph_set_pin_value(arguments):
    blueprint_path = arguments["blueprint"]
    graph_name = arguments.get("graph", "EventGraph")
    result = parse_graph_result(
        graph_bridge().set_pin_default_value(
            blueprint_path,
            graph_name,
            resolve_graph_node(blueprint_path, graph_name, arguments["node"]),
            arguments["pin"],
            str(arguments["value"]),
        )
    )
    mark_changed(blueprint_path)
    return result


ACTION_HANDLERS = {
    "system.capabilities": execute_system_capabilities,
    "system.describe_actions": execute_describe_actions,
    "content.create_folder": execute_create_folder,
    "content.list": execute_list_content,
    "asset.inspect": execute_inspect_asset,
    "material.create": execute_create_material,
    "material.inspect": execute_inspect_material,
    "material_instance.create": execute_create_material_instance,
    "material_instance.set_parameters": execute_set_material_instance_parameters,
    "blueprint.create": execute_create_blueprint,
    "blueprint.inspect": execute_inspect_blueprint,
    "blueprint.compile": execute_compile_blueprint,
    "blueprint.edit": execute_edit_blueprint,
    "blueprint.graph.inspect": execute_graph_inspect,
    "blueprint.graph.add_node": execute_graph_add_node,
    "blueprint.graph.connect": execute_graph_connect,
    "blueprint.graph.set_pin_value": execute_graph_set_pin_value,
    "level.inspect": execute_inspect_level,
    "level.spawn_actor": execute_spawn_actor,
    "level.set_actor_transform": execute_set_actor_transform,
    "level.set_actor_property": execute_set_actor_property,
    "project.save": execute_save_project,
}


MUTATING_ACTIONS = {
    "content.create_folder",
    "material.create",
    "material_instance.create",
    "material_instance.set_parameters",
    "blueprint.create",
    "blueprint.compile",
    "blueprint.edit",
    "blueprint.graph.add_node",
    "blueprint.graph.connect",
    "blueprint.graph.set_pin_value",
    "level.spawn_actor",
    "level.set_actor_transform",
    "level.set_actor_property",
}


def validate_document(document):
    require(isinstance(document, dict), "Document root must be an object", "invalid_document")
    require(
        document.get("format_version") == "1.0",
        "Unsupported format_version",
        "unsupported_format",
    )
    commands = document.get("commands")
    require(isinstance(commands, list), "'commands' must be an array", "invalid_document")
    require(
        len(commands) <= MAX_COMMANDS,
        "Too many commands; maximum is " + str(MAX_COMMANDS),
        "too_many_commands",
    )
    seen = set()
    for index, command in enumerate(commands):
        require(
            isinstance(command, dict),
            "Command at index {} must be an object".format(index),
            "invalid_command",
        )
        command_id = command.get("id")
        action = command.get("action")
        require(
            isinstance(command_id, str) and command_id,
            "Command id must be a non-empty string",
            "invalid_command",
        )
        require(command_id not in seen, "Duplicate command id: " + command_id, "duplicate_command_id")
        require(action in ACTION_HANDLERS, "Unsupported action: " + str(action), "unsupported_action")
        require(
            isinstance(command.get("arguments", {}), dict),
            "arguments must be an object: " + command_id,
            "invalid_arguments",
        )
        dependencies = command.get("depends_on", [])
        require(
            isinstance(dependencies, list),
            "depends_on must be an array: " + command_id,
            "invalid_dependencies",
        )
        require(
            all(isinstance(item, str) for item in dependencies),
            "depends_on values must be strings",
            "invalid_dependencies",
        )
        missing = [item for item in dependencies if item not in seen]
        require(
            not missing,
            "Dependencies must refer to earlier commands: " + ", ".join(missing),
            "invalid_dependencies",
        )
        seen.add(command_id)
    return commands


def execute_command(command):
    global CURRENT_CHANGED_OBJECTS
    CURRENT_CHANGED_OBJECTS = []
    command_id = command.get("id")
    action = command.get("action")
    require(command_id, "Command does not contain an id")
    require(action, "Command does not contain an action")
    handler = ACTION_HANDLERS.get(action)
    require(handler is not None, "Unsupported action: " + action)
    log("Executing: " + command_id + " -> " + action)
    if action in MUTATING_ACTIONS:
        transaction = unreal.ScopedEditorTransaction("Codex: " + action)
        try:
            data = handler(command.get("arguments", {}))
        except Exception:
            transaction.cancel()
            raise
        finally:
            del transaction
    else:
        data = handler(command.get("arguments", {}))
    return {
        "id": command_id,
        "action": action,
        "success": True,
        "data": data,
        "changed_objects": list(CURRENT_CHANGED_OBJECTS),
    }


def main():
    GRAPH_NODE_ALIASES.clear()
    result = {
        "format_version": "1.0",
        "harness_version": HARNESS_VERSION,
        "run_id": str(uuid.uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "commands": [],
        "errors": [],
        "changed_objects": [],
    }
    try:
        document = load_json_file(ACTIONS_FILE)
        commands = validate_document(document)
        if document.get("dry_run", False):
            result["dry_run"] = True
            result["plan"] = [
                {
                    "id": command["id"],
                    "action": command["action"],
                    "mutating": command["action"] in MUTATING_ACTIONS,
                    "depends_on": command.get("depends_on", []),
                }
                for command in commands
            ]
            commands = []
        command_status = {}
        for command in commands:
            command_id = command.get("id", "<missing id>")
            failed_dependencies = [
                dependency
                for dependency in command.get("depends_on", [])
                if command_status.get(dependency) is not True
            ]
            if failed_dependencies:
                dependency_error = HarnessError(
                    "dependency_failed",
                    "Failed dependencies: " + ", ".join(failed_dependencies),
                )
                result["commands"].append(
                    {
                        "id": command_id,
                        "action": command.get("action"),
                        "success": False,
                        "skipped": True,
                        "error": str(dependency_error),
                        "error_code": dependency_error.code,
                        "changed_objects": [],
                    }
                )
                command_status[command_id] = False
                result["success"] = False
                continue
            try:
                command_result = execute_command(command)
                result["commands"].append(command_result)
                merge_changed(result["changed_objects"], command_result["changed_objects"])
                command_status[command_id] = True
            except Exception as error:
                error_text = str(error)
                log_error(command_id + ": " + error_text)
                result["commands"].append(
                    {
                        "id": command_id,
                        "action": command.get("action"),
                        "success": False,
                        "error": error_text,
                        "error_code": getattr(error, "code", "execution_failed"),
                        "changed_objects": list(CURRENT_CHANGED_OBJECTS),
                    }
                )
                merge_changed(result["changed_objects"], CURRENT_CHANGED_OBJECTS)
                result["errors"].append(error_record(error, command_id, True))
                command_status[command_id] = False
                result["success"] = False
    except Exception as error:
        result["success"] = False
        result["errors"].append(error_record(error, None, True))
        log_error(str(error))

    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    save_json_file(RESULT_FILE, result)
    if result["success"]:
        log("All commands completed successfully")
    else:
        log_error("Some commands failed")
    log("Result file: " + RESULT_FILE)


main()
