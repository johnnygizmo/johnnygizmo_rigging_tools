import bpy  # type: ignore
import bmesh  # type: ignore
from mathutils import Vector, Matrix  # type: ignore


class MESH_OT_johnnygizmo_bone_per_vertex(bpy.types.Operator):
    bl_idname = "mesh.johnnygizmo_bone_per_vertex"
    bl_label = "Create Bone Per Vertex"
    bl_description = "Create a bone in the parent armature for each selected vertex"
    bl_options = {'REGISTER', 'UNDO'}

    bone_length: bpy.props.FloatProperty(
        name="Bone Length",
        description="Length of created bones",
        default=1.0,
        min=0.01,
        max=100.0,
        step=0.1,
    )  # type: ignore

    direction: bpy.props.EnumProperty(
        name="Direction",
        description="Direction each bone should point",
        items=[
            ('X+', "+X (Global)", "Positive X axis"),
            ('X-', "-X (Global)", "Negative X axis"),
            ('Y+', "+Y (Global)", "Positive Y axis"),
            ('Y-', "-Y (Global)", "Negative Y axis"),
            ('Z+', "+Z (Global)", "Positive Z axis"),
            ('Z-', "-Z (Global)", "Negative Z axis"),
            ('NORMAL', "Vertex Normal", "Along vertex normal direction"),
        ],
        default='Z+',
    )  # type: ignore

    def invoke(self, context, event):
        # Validate context
        if context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Must be in Edit Mode on a Mesh")
            return {'CANCELLED'}

        mesh_obj = context.edit_object
        if mesh_obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}

        if not mesh_obj.parent or mesh_obj.parent.type != 'ARMATURE':
            self.report({'ERROR'}, "Mesh must have an armature parent")
            return {'CANCELLED'}

        # Get selected vertices
        bm = bmesh.from_edit_mesh(mesh_obj.data)
        selected_verts = [v for v in bm.verts if v.select]

        if not selected_verts:
            self.report({'ERROR'}, "No vertices selected")
            return {'CANCELLED'}

        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        # Validate context
        if context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Must be in Edit Mode on a Mesh")
            return {'CANCELLED'}

        mesh_obj = context.edit_object
        if mesh_obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}

        # Check for armature parent
        if not mesh_obj.parent or mesh_obj.parent.type != 'ARMATURE':
            self.report({'ERROR'}, "Mesh must have an armature parent")
            return {'CANCELLED'}

        armature_obj = mesh_obj.parent

        # Get selected vertices and their normals
        bm = bmesh.from_edit_mesh(mesh_obj.data)
        selected_verts = [v for v in bm.verts if v.select]

        if not selected_verts:
            self.report({'ERROR'}, "No vertices selected")
            return {'CANCELLED'}

        # Ensure normals are calculated
        bm.normal_update()

        # Extract all vertex data while in edit mode (before switching modes)
        # Store as tuples to avoid BMesh reference issues
        vert_data = []
        for i, vert in enumerate(selected_verts):
            # Get vertex position in world space
            vert_pos_world = mesh_obj.matrix_world @ vert.co
            
            # Get vertex normal in world space if needed
            vert_normal_world = None
            if self.direction == 'NORMAL':
                normal_local = vert.normal.copy()
                vert_normal_world = mesh_obj.matrix_world.to_3x3() @ normal_local
                vert_normal_world = vert_normal_world.normalized()
            
            vert_data.append({
                'pos_world': vert_pos_world,
                'normal_world': vert_normal_world,
                'index': vert.index  # Store vertex index for vertex group assignment
            })

        # Get direction vector based on direction setting
        def get_direction_vec(direction_key, vert_normal=None):
            if direction_key == 'NORMAL':
                # Use vertex normal
                if vert_normal is not None:
                    return vert_normal
                else:
                    return Vector((0, 0, 1))
            else:
                # Use global axis
                axis_map = {
                    'X+': Vector((1, 0, 0)),
                    'X-': Vector((-1, 0, 0)),
                    'Y+': Vector((0, 1, 0)),
                    'Y-': Vector((0, -1, 0)),
                    'Z+': Vector((0, 0, 1)),
                    'Z-': Vector((0, 0, -1)),
                }
                return axis_map[direction_key]

        # Switch to object mode to modify armature
        bpy.ops.object.mode_set(mode='OBJECT')

        # Change to armature edit mode
        context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='EDIT')

        # Get armature data
        armature_data = armature_obj.data
        edit_bones = armature_data.edit_bones

        # Deselect all bones first
        for bone in edit_bones:
            bone.select = False

        # Create a bone for each selected vertex
        new_bone_info = []  # Store (actual_bone_name, vertex_index) pairs
        for i, vert_info in enumerate(vert_data):
            # Get direction vector
            direction_vec = get_direction_vec(self.direction, vert_info['normal_world'])
            vert_pos_world = vert_info['pos_world']
            vert_index = vert_info['index']

            # Convert world space positions to armature space
            vert_pos_armature = armature_obj.matrix_world.inverted() @ vert_pos_world
            direction_armature = armature_obj.matrix_world.to_3x3().inverted() @ direction_vec

            # Create bone
            bone_name = f"Bone_Vertex_{i:03d}"
            bone = edit_bones.new(bone_name)
            bone.head = vert_pos_armature
            bone.tail = vert_pos_armature + direction_armature.normalized() * self.bone_length
            
            # Store the actual bone name (Blender may have renamed it with .001 suffix)
            new_bone_info.append((bone.name, vert_index))

        # Switch back to object mode to apply changes
        bpy.ops.object.mode_set(mode='OBJECT')

        # Create vertex groups for each bone on the mesh using actual bone names
        mesh_data = mesh_obj.data
        for bone_name, vert_index in new_bone_info:
            # Create vertex group if it doesn't exist
            if bone_name not in mesh_obj.vertex_groups:
                vgroup = mesh_obj.vertex_groups.new(name=bone_name)
            else:
                vgroup = mesh_obj.vertex_groups[bone_name]
            
            # Assign the vertex to the group with weight 1.0
            vgroup.add([vert_index], 1.0, 'REPLACE')

        # Return to mesh as active object so user can continue working
        context.view_layer.objects.active = mesh_obj

        self.report({'INFO'}, f"Created {len(vert_data)} bones")
        return {'FINISHED'}


def menu_func(self, context):
    self.layout.operator(MESH_OT_johnnygizmo_bone_per_vertex.bl_idname)


def register():
    bpy.utils.register_class(MESH_OT_johnnygizmo_bone_per_vertex)
    bpy.types.VIEW3D_MT_edit_mesh.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_edit_mesh.remove(menu_func)
    bpy.utils.unregister_class(MESH_OT_johnnygizmo_bone_per_vertex)
