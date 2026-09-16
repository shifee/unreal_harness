import json
import os
import re
import traceback

import unreal


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIONS_FILE = os.path.join(SCRIPT_DIR, "actions.json")
RESULT_FILE = os.path.join(SCRIPT_DIR, "result.json")


def log(message):
    unreal.log("[AI EXECUTOR] " + str(message))


def log_error(message):
    unreal.log_error("[AI EXECUTOR] " + str(message))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


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
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def execute_create_folder(arguments):
    path = validate_game_path(arguments["path"])
    if unreal.EditorAssetLibrary.does_directory_exist(path):
        return {"created": False, "path": path, "message": "Directory already exists"}
    success = unreal.EditorAssetLibrary.make_directory(path)
    require(success, "Could not create directory: " + path)
    return {"created": True, "path": path}


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
    return {
        "asset_path": object_path,
        "generated_class_path": object_path + "_C",
    }


def get_blueprint_components(blueprint):
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = subsystem.k2_gather_subobject_data_for_blueprint(blueprint)
    require(len(handles) > 0, "Blueprint does not contain subobject data")
    library = unreal.SubobjectDataBlueprintFunctionLibrary
    components = {}
    component_handles = {}
    for handle in handles:
        try:
            display_name = str(library.get_display_name(handle))
            component = library.get_object(library.get_data(handle))
            if component is not None:
                components[display_name] = component
                components[component.get_name()] = component
            component_handles[display_name] = handle
        except Exception:
            pass
    return subsystem, handles[0], components, component_handles


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
    component = library.get_object(library.get_data(new_handle))
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


def set_component_property(components, operation):
    component_name = operation["component_name"]
    component = components.get(component_name)
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


def set_component_transform(components, operation):
    component_name = operation["component_name"]
    component = components.get(component_name)
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
    return {
        "actor_name": actor.get_name(),
        "actor_label": actor.get_actor_label(),
        "class": class_path,
    }


def execute_save_project(arguments):
    if arguments.get("save_level", True):
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    if arguments.get("save_assets", True):
        unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    return {
        "level_saved": arguments.get("save_level", True),
        "assets_saved": arguments.get("save_assets", True),
    }


ACTION_HANDLERS = {
    "content.create_folder": execute_create_folder,
    "blueprint.create": execute_create_blueprint,
    "blueprint.edit": execute_edit_blueprint,
    "level.spawn_actor": execute_spawn_actor,
    "project.save": execute_save_project,
}


def execute_command(command):
    command_id = command.get("id")
    action = command.get("action")
    require(command_id, "Command does not contain an id")
    require(action, "Command does not contain an action")
    handler = ACTION_HANDLERS.get(action)
    require(handler is not None, "Unsupported action: " + action)
    log("Executing: " + command_id + " -> " + action)
    return {
        "id": command_id,
        "action": action,
        "success": True,
        "data": handler(command.get("arguments", {})),
    }


def main():
    result = {"success": True, "commands": [], "errors": []}
    try:
        document = load_json_file(ACTIONS_FILE)
        commands = document.get("commands", [])
        require(isinstance(commands, list), "'commands' must be an array")
        command_status = {}
        for command in commands:
            command_id = command.get("id", "<missing id>")
            failed_dependencies = [
                dependency
                for dependency in command.get("depends_on", [])
                if command_status.get(dependency) is not True
            ]
            if failed_dependencies:
                result["commands"].append(
                    {
                        "id": command_id,
                        "action": command.get("action"),
                        "success": False,
                        "skipped": True,
                        "error": "Failed dependencies: " + ", ".join(failed_dependencies),
                    }
                )
                command_status[command_id] = False
                result["success"] = False
                continue
            try:
                command_result = execute_command(command)
                result["commands"].append(command_result)
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
                    }
                )
                result["errors"].append(
                    {
                        "command_id": command_id,
                        "message": error_text,
                        "traceback": traceback.format_exc(),
                    }
                )
                command_status[command_id] = False
                result["success"] = False
    except Exception as error:
        result["success"] = False
        result["errors"].append(
            {"command_id": None, "message": str(error), "traceback": traceback.format_exc()}
        )
        log_error(str(error))

    save_json_file(RESULT_FILE, result)
    if result["success"]:
        log("All commands completed successfully")
    else:
        log_error("Some commands failed")
    log("Result file: " + RESULT_FILE)


main()
