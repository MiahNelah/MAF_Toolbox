bl_info = {
    "name": "Modular Armor Framework",
    "blender": (4, 0, 0),
    "category": "Object",
    "description": "Ajoute un menu rapide avec des actions personnalisées",
}
import bpy
import re
import uuid
import json
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty
from collections import defaultdict

class DefinitionSaveFile(Operator, ExportHelper):
    """Generate Definition File"""
    bl_idname = "wm.custom_save_file"
    bl_label = "Generate Definition File"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        # Get the data stored in bpy.types.Scene
        custom_data = context.scene.custom_export_data

        # Write content to the file
        with open(self.filepath, 'w') as file:
            file.write(custom_data)

        print(f"File saved at: {self.filepath}")
        return {'FINISHED'}
        print(f"File saved at: {self.filepath}")
        return {'FINISHED'}

bpy.types.Scene.custom_export_data = StringProperty(name="Export Data")
bpy.utils.register_class(DefinitionSaveFile)


def find_main_group(group_id, groups):
    if group_id-100 in groups:
        return group_id - 100
    else:
        return group_id

def group_meshes():
    collections_dict = {}

    for collection in bpy.data.collections:
        if not collection.name.endswith(".mesh"):
            continue

        meshes_by_group = defaultdict(list)
        seen_meshes = set()

        for obj in collection.objects:
            if obj.type == "MESH":
                meshname = collection.name.replace(".mesh", "")
                match = re.match(r"Group_(\d+)_Sub_(\d+)__.*", obj.name)
                if match:
                    group_id = int(match.group(1))
                    if group_id > 0:
                        main_group = find_main_group(group_id, meshes_by_group)
                        group = {
                            "id": group_id,
                            "name": obj.name,
                            "hidden": group_id - 100 == main_group
                        }
                        key=meshname+"/"+match.group(1)
                        print(key)
                        if key not in seen_meshes:
                            seen_meshes.add(key)
                            meshes_by_group[main_group].append(group)
        collections_dict[meshname] = meshes_by_group
    return collections_dict

def print_meshes(meshes, collection_name, inverted):
    result =  [f'"{"!" if inverted and x["hidden"] else ""}{collection_name}/{x["id"]}"' for x in meshes]
    return ', '.join(list(set(result)))

def create_category(collection_name):
    name = ""
    match collection_name[-1]:
        case "1": name = "Arms"
        case "2": name = "Body"
        case "3": name = "Head"
        case "4": name = "Legs"
        case "5": name = "Waist"
        case "6": name = "Slinger"
        case _: name = ""
    return f'{{"id": "{str(uuid.uuid4())}", "label": "{name}", "entries": [%ENTRIES%] }}'

def get_hidden(data):
    result = []
    for col_name, groups in data.items():
        for group, mesh in sorted(groups.items()):
            hidden = [x for x in mesh if x["hidden"] == True]
            if len(hidden)>0:
                result.extend([f'"{col_name}/{x["id"]}"' for x in hidden])
    return ', '.join(result)


class GenerateDefinitionOperator(bpy.types.Operator):
    bl_idname = "object.maf_generate_definition"
    bl_label = "Generate definition"
    bl_options = {'REGISTER'}


    def execute(self, context):
        cat = []
        result = group_meshes()

        for col_name, groups in result.items():                        
            col_def = create_category(col_name)
            col_output = []
            for group, mesh in sorted(groups.items()):
                if mesh:
                    inverted = False
                    if len(mesh) > 1:
                        ids = [x.get("id") for x in mesh if x is not None]
                        _min = min(ids)
                        _max = max(ids)
                        inverted = _max >= _min+100

                    for x in mesh:
                        _uuid = str(uuid.uuid4())
                        _meshes = print_meshes(mesh, col_name, inverted)
                        col_output.append(f'{{ "id": "{_uuid}", "name": "", "mesh": [{_meshes}] }}')
            col_def = col_def.replace("%ENTRIES%", ','.join(col_output))
            cat.append(col_def)

        doc = f'''{{
            "id": "{str(uuid.uuid4())}",
            "name": "",
            "hidden": [{get_hidden(result)}],
            "categories": [%CATEGORIES%]
        }}'''
        doc = doc.replace("%CATEGORIES%", ','.join(cat))
        doc = json.dumps(json.loads(doc), indent=4)        

        bpy.context.scene.custom_export_data = doc
        bpy.ops.wm.custom_save_file('INVOKE_DEFAULT')

        return {'FINISHED'}

class AssignGroupNumberOperator(bpy.types.Operator):
    """Assign a unique Group Number to selected group mesh, then hide them"""
    bl_idname = "object.maf_update_group_xx"
    bl_label = "Assign Group Number"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        pattern = re.compile(r"Group_(\d+)_Sub_(\d+)(__.*)")

        selected_objects = [obj for obj in context.selected_objects if pattern.match(obj.name)]
        
        if not selected_objects:
            self.report({'WARNING'}, "No valid groups selected!")
            return {'CANCELLED'}

        collections = set()
        for obj in selected_objects:
            if obj.users_collection:
                collections.update(obj.users_collection)

        if len(collections) > 1:
            self.report({'ERROR'}, "The selected objects belong to several collections!")
            return {'CANCELLED'}

        collection = collections.pop()  
        max_xx = 0

        for obj in collection.objects:
            match = pattern.match(obj.name)
            if match:
                max_xx = max(max_xx, int(match.group(1)))

        new_xx = min(max_xx + 1, 256)
        new_xx_str = f"{new_xx:02d}"

        for obj in selected_objects:
            match = pattern.match(obj.name)
            if match:
                obj.name = f"Group_{new_xx_str}_Sub_{match.group(2)}{match.group(3)}"
                obj.hide_set(True)   

        self.report({'INFO'}, f"New assigned group: {new_xx_str}. Hidden objects.")
        return {'FINISHED'}

class ResetGroupsOperator(bpy.types.Operator):
    """Reset all group number to 0 for selected group meshs"""
    bl_idname = "object.maf_reset_group_xx"
    bl_label = "Reset Groups Numbers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        pattern = re.compile(r"Group_(\d+)_Sub_(\d+)(__.*)")
        new_xx_str = "0"

        selected_objects = [obj for obj in context.selected_objects if pattern.match(obj.name)]

        if selected_objects:
            for obj in selected_objects:
                match = pattern.match(obj.name)
                if match:
                    obj.name = f"Group_{new_xx_str}_Sub_{match.group(2)}{match.group(3)}"

            self.report({'INFO'}, "Group reset to 0 for selected objects.")
            return {'FINISHED'}

        selected_collections = [col for col in bpy.context.view_layer.layer_collection.children if col.collection in bpy.data.collections and col.collection.objects]

        if len(selected_collections) != 1:
            self.report({'ERROR'}, "Select a single collection to reset all its items!")
            return {'CANCELLED'}

        collection = selected_collections[0].collection

        for obj in collection.objects:
            match = pattern.match(obj.name)
            if match:
                obj.name = f"Group_{new_xx_str}_Sub_{match.group(2)}{match.group(3)}"

        self.report({'INFO'}, f"Group reset to 0 for all objects in collection {collection.name}.")
        return {'FINISHED'}

class MAFPanel(bpy.types.Panel):
    """Panneau pour renommer et masquer les groupes"""
    bl_label = "Modular Armor Framework"
    bl_idname = "VIEW3D_PT_MAFPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Modular Armor Framework"

    def draw(self, context):
        layout = self.layout
        layout.operator(AssignGroupNumberOperator.bl_idname, text="Assign Group Number")
        layout.separator()        
        layout.operator(GenerateDefinitionOperator.bl_idname, text="Generate Definition File")
        layout.separator()
        layout.operator(ResetGroupsOperator.bl_idname, text="Reset Groups Numbers")

def register():
    bpy.utils.register_class(AssignGroupNumberOperator)
    bpy.utils.register_class(GenerateDefinitionOperator)
    bpy.utils.register_class(ResetGroupsOperator)
    bpy.utils.register_class(MAFPanel)

def unregister():
    bpy.utils.unregister_class(AssignGroupNumberOperator)
    bpy.utils.unregister_class(GenerateDefinitionOperator)
    bpy.utils.unregister_class(ResetGroupsOperator)
    bpy.utils.unregister_class(MAFPanel)

if __name__ == "__main__":
    register()
