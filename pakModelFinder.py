import os, argparse, asyncio, struct, json, logging, time, math
from collections import defaultdict
from typing import Tuple

#######################################################################################################
# Log Colored Formatter

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.DEBUG:
            record.msg = f"\033[0m[DEBG] {record.msg}\033[0m"
        elif record.levelno == logging.INFO:
            record.msg = f"\033[32m[INFO] {record.msg}\033[0m"
        elif record.levelno == logging.WARNING:
            record.msg = f"\033[33m[WARN] {record.msg}\033[0m"
        elif record.levelno == logging.ERROR:
            record.msg = f"\033[31m[ERRO] {record.msg}\033[0m"
        elif record.levelno == logging.CRITICAL:
            record.msg = f"\033[35m[CRIT] {record.msg}\033[0m"
        return super().format(record)
 
LOG_FORMATTER = '%(message)s' # '[%(asctime)s]%(message)s'
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter(LOG_FORMATTER))
logger = logging.getLogger('main')
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

#######################################################################################################
# Binary stream reader

class BinStreamReader:
    @staticmethod
    def read_uint32_data(file, b_print=False) -> list[int]:
        array = []
        while True:
            data = file.read(4)
            if len(data) < 4:
                return []
            val = struct.unpack('>I', data)[0]
            if val == 0:
                break
            array.append(val)
        if b_print:
            for num in array:
                print(f'0x{num:08X}')
        return array
    @staticmethod
    def read_string(file, b_print=False) -> str:
        result = bytearray()
        while True:
            byte = file.read(1)
            if not byte or byte == b'\x00':
                file.seek(-1, os.SEEK_CUR)
                break
            result.extend(byte)
        rtn = result.decode('utf-8')
        if b_print:
            print(rtn)
        return rtn

class ReformValue:
    @staticmethod
    def I2f(uint32_val: int) -> float:
        binary_data = struct.pack('I', uint32_val)
        return struct.unpack('f', binary_data)[0]

#######################################################################################################
# PAK Header

class PakHeader:
    uint32_prefix       = 0
    uint32_unk0         = 0
    uint32_unk1         = 0
    uint32_entry_ptr    = 0
    uint32_edo_ptr      = 0
    uint32_padding0     = 0
    uint32_padding1     = 0
    uint32_padding2     = 0
    file_size   = 0
    file        = None
    
    def __init__(self, file):
        self.file = file
        # Get file size
        self.file.seek(0, os.SEEK_END)
        self.file_size = self.file.tell()
        self.file.seek(0, os.SEEK_SET)
        # Read header
        data = self.file.read(4 * 8)
        if len(data) < 4 * 8:
            logger.error('PAK header file is too small')
            return
        values = struct.unpack('>8I', data)
        self.uint32_prefix          = values[0]
        self.uint32_unk0            = values[1]
        self.uint32_unk1            = values[2]
        self.uint32_entry_ptr       = values[3]
        self.uint32_edo_ptr         = values[4]
        self.uint32_padding0        = values[5]
        self.uint32_padding1        = values[6]
        self.uint32_padding2        = values[7]
        
    def is_mesh_pak(self) -> bool:
        if self.uint32_prefix != 0x020E0000:
            logger.error('PAK header prefix is not correct')
            return False
        if self.uint32_unk0 != 0x00000044:
            logger.error(f'This PAK may not be a standard mesh package (unk0=0x{self.uint32_unk0:08X})')
            return False
        if self.uint32_unk1 != 0x00010001 and self.uint32_unk1 != 0x00010002:
            logger.error(f'This PAK may not be a standard mesh package (unk1=0x{self.uint32_unk1:08X})')
            return False
        if self.uint32_entry_ptr >= self.file_size or self.uint32_entry_ptr == 0:
            logger.error('PAK Entry offset pointer overflow')
            return False
        if self.uint32_edo_ptr >= self.file_size or self.uint32_edo_ptr == 0:
            logger.error('PAK EDO offset pointer overflow')
            return False
        return True
        
#######################################################################################################
# Entry Pointer

class EntryPointer:
    uint32_mesh_ptr     = 0
    uint32_unk0         = 0
    uint32_bone_ptr     = 0
    uint32_unk1         = 0
    uint32_unk2_ptr     = 0
    file_size   = 0
    file        = None
    
    def __init__(self, file, offset: int):
        self.file = file
        # Get file size
        self.file.seek(0, os.SEEK_END)
        self.file_size = self.file.tell()
        self.file.seek(offset, os.SEEK_SET)
        # Read entry data
        data = self.file.read(4 * 5)
        if len(data) < 4 * 5:
            logger.error('PAK entry data size is too small')
            return
        values = struct.unpack('>5I', data)
        self.uint32_mesh_ptr    = values[0]
        self.uint32_unk0        = values[1]
        self.uint32_bone_ptr    = values[2]
        self.uint32_unk1        = values[3]
        self.uint32_unk2_ptr    = values[4]
        
    def is_valid_data(self) -> bool:
        if self.uint32_mesh_ptr >= self.file_size or self.uint32_mesh_ptr == 0:
            logger.error(f'Invalid mesh offset pointer (0x{self.uint32_mesh_ptr:08X})')
            return False
        if self.uint32_bone_ptr >= self.file_size or self.uint32_bone_ptr == 0:
            logger.error(f'Invalid bone offset pointer (0x{self.uint32_bone_ptr:08X})')
            return False
        if self.uint32_unk2_ptr >= self.file_size or self.uint32_unk2_ptr == 0:
            logger.error(f'Invalid unk2 offset pointer (0x{self.uint32_unk2_ptr:08X})')
            return False
        return True
        
#######################################################################################################
# Mesh Paser

class MeshData:
    name            = ''
    d_offset        = 0
    # Polygon Param Set -------------------
    f_count         = 0
    faces           = []
    face_addr       = 0
    min_f_idx       = 0
    max_f_idx       = 0
    # Vertex Param Set -------------------
    v_count         = 0
    positions       = []
    position_addr   = 0
    normals         = []
    normal_addr     = 0
    tangents        = []
    tangent_addr    = 0
    binormals       = []
    binormal_addr   = 0
    weights         = []
    weights_addr    = 0
    blend_idx_list  = []
    blend_idx_addr  = 0
    max_blend_idx   = 0
    bone_indices    = []
    uvs             = []
    uv_addr         = 0
    # Other Param Set -------------------
    eof_addr        = 0
    index           = 0
    
    def __init__(self, name: str, v_count: int, f_count: int, b_indices: list[int], d_offset: int):
        self.index = 0
        self.name = name
        self.v_count = v_count
        self.f_count = f_count
        self.d_offset = d_offset
        self.bone_indices = b_indices
        
    def start_paser(self, idx: int, file):
        self.index = idx
        file.seek(self.d_offset, os.SEEK_SET)
        if self.__parse_faces_step__(file) == 0:
            return
        if self.__parse_vertices_step__(file) == 0:
            return
        if self.__parse_uv_step__(file) == 0:
            return
        self.eof_addr = file.tell()

    def get_axe_json_data(self):
        return {
            "MeshName"              : self.name,
            "VertexCount"           : self.v_count,
            "PolygonCount"          : self.f_count,
            "HasNormal"             : True,
            "HasTexcoord"           : True,
            "HasTangent"            : True,
            "HasBinormal"           : True,
            "HasSkinningInfo"       : True,
            "FlipUV"                : True,
            "UVSetCount"            : 1,
            "UVSetLabels"           : [ "UV0" ],
            "VertexParamSetCount"   : 1,
            "PolygonParamSetCount"  : 1,
            "VertexParamSets"       : [{
                "VertexCount"           : self.v_count,
                "PerVertexBoneCount"    : 3,
                "HasBoneIndexMapping"   : True,
                "UseUserDefinedIndices" : True,
                "UVFactors"             : [ "Auto" ],
                "PositionRec"   : {
                    "Address"   : self.position_addr,
                    "Stride"    : 64,
                    "DataType"  : "Float"
                },
                "NormalRec"     : {
                    "Address"   : self.normal_addr,
                    "Stride"    : 64,
                    "DataType"  : "Float"
                },
                "TexcoordRecs"  : [{
                    "Address"   : self.uv_addr,
                    "Stride"    : 4,
                    "DataType"  : "Half-float"
                }],
                "TangentRec"    : {
                    "Address"   : self.tangent_addr,
                    "Stride"    : 64,
                    "DataType"  : "Float"
                },
                "BinormalRec"   : {
                    "Address"   : self.binormal_addr,
                    "Stride"    : 64,
                    "DataType"  : "Float"
                },
                "BlendWeightRec": {
                    "Address"   : self.weights_addr,
                    "Stride"    : 64,
                    "DataType"  : "Float"
                },
                "BlendIndexRec" : {
                    "Address"   : self.blend_idx_addr,
                    "Stride"    : 64,
                    "DataType"  : "UINT8"
                },
                "MappingBoneIndices" : {
                    "Count" : len(self.bone_indices),
                    "UserDefinedIndices" : self.bone_indices
                }
            }],
            "PolygonParamSets"      : [{
                "DecodedPolygonCount"       : self.f_count,
                "PolygonVertexIndexCount"   : self.f_count * 3,
                "Address"                   : self.face_addr,
                "DataType"                  : "UINT16",
                "Encoding"                  : "Triangle"
            }]
        }
        
    def __parse_faces_step__(self, file) -> int:
        self.face_addr = file.tell()
        dlen = self.f_count * 3 * 2
        hnum = self.f_count * 3
        data = file.read(dlen)
        if len(data) < dlen:
            logger.error(f'[idx={self.index:02}] Mesh face data size is too small')
            return 0
        max_val = 0x0000
        min_val = 0xFFFF
        values = struct.unpack(f'>{hnum}H', data)
        for i in range(self.f_count):
            pos = i * 3
            if max_val < values[pos + 0]:
                max_val = values[pos + 0]
            if max_val < values[pos + 1]:
                max_val = values[pos + 1]
            if max_val < values[pos + 2]:
                max_val = values[pos + 2]
            if min_val > values[pos + 0]:
                min_val = values[pos + 0]
            if min_val > values[pos + 1]:
                min_val = values[pos + 1]
            if min_val > values[pos + 2]:
                min_val = values[pos + 2]
            face = [values[pos + 0], values[pos + 1], values[pos + 2]]
            self.faces.append(face)
        if max_val + 1 > self.v_count:
            logger.error(f'[idx={self.index:02}] Mismatch of faces and vertices ({max_val} > {self.v_count - 1})')
            return 0
        self.min_f_idx = min_val
        self.max_f_idx = max_val
        remainder = dlen % 16
        if remainder > 0:
            padding_len = 16 - remainder
            file.read(padding_len)
        return file.tell()
        
    def __parse_vertices_step__(self, file) -> int:
        bone_indice_size = len(self.bone_indices)
        warning_indice_cnt = 0
        for i in range(self.v_count):
            # Read position
            if i == 0:
                self.position_addr = file.tell()
            data = file.read(12)
            if len(data) < 12:
                logger.error(f'[idx={self.index:02}] Cannot read vertice.position')
                return 0
            values = struct.unpack('>3f', data)
            xyz = [values[0], values[1], values[2]]
            self.positions.append(xyz)
            # Read normal -----------------------------------
            if i == 0:
                self.normal_addr = file.tell()
            data = file.read(12)
            if len(data) < 12:
                logger.error(f'[idx={self.index:02}] Cannot read vertice.normal')
                return 0
            values = struct.unpack('>3f', data)
            normal = [values[0], values[1], values[2]]
            self.normals.append(normal)
            # Read tangent ----------------------------------
            if i == 0:
                self.tangent_addr = file.tell()
            data = file.read(12)
            if len(data) < 12:
                logger.error(f'[idx={self.index:02}] Cannot read vertice.tangent')
                return 0
            values = struct.unpack('>3f', data)
            tangent = [values[0], values[1], values[2]]
            self.tangents.append(tangent)
            # Read binormal ---------------------------------
            if i == 0:
                self.binormal_addr = file.tell()
            data = file.read(12)
            if len(data) < 12:
                logger.error(f'[idx={self.index:02}] Cannot read vertice.binormal')
                return 0
            values = struct.unpack('>3f', data)
            binormal = [values[0], values[1], values[2]]
            self.binormals.append(binormal)
            # Read weight slot ---------------------------------
            if i == 0:
                self.weights_addr = file.tell()
            data = file.read(12)
            if len(data) < 12:
                logger.error(f'[idx={self.index:02}] Cannot read vertice.weights')
                return 0
            values = struct.unpack('>3f', data)
            weights = [values[0], values[1], values[2]]
            self.weights.append(weights)
            # Read blend index slot ---------------------------------
            if i == 0:
                self.blend_idx_addr = file.tell()
            data = file.read(4)
            if len(data) < 4:
                logger.error(f'[idx={self.index:02}] Cannot read vertice.blend_index')
                return 0
            values = struct.unpack('>4B', data)
            if self.max_blend_idx < values[0]:
                self.max_blend_idx = values[0]
            if self.max_blend_idx < values[1]:
                self.max_blend_idx = values[1]
            if self.max_blend_idx < values[2]:
                self.max_blend_idx = values[2]
            if values[0] >= bone_indice_size:
                warning_indice_cnt += 1
            if values[1] >= bone_indice_size:
                warning_indice_cnt += 1
            if values[2] >= bone_indice_size:
                warning_indice_cnt += 1
            a1 = self.bone_indices[values[0]] if values[0] < bone_indice_size else values[0]
            a2 = self.bone_indices[values[1]] if values[1] < bone_indice_size else values[1]
            a3 = self.bone_indices[values[2]] if values[2] < bone_indice_size else values[2]
            self.blend_idx_list.append([a1, a2, a3])
        if warning_indice_cnt > 0:
            logger.warning(f'[idx={self.index:02}] There are {warning_indice_cnt} bone indices may not correct')
        return file.tell()
        
    def __parse_uv_step__(self, file) -> int:
        self.uv_addr = file.tell()
        dlen = self.v_count * 2 * 2
        for i in range(self.v_count):
            data = file.read(4)
            if len(data) < 4:
                logger.error(f'[idx={self.index:02}] Cannot read vertice.texcoord')
                return 0
            values = struct.unpack('>2e', data)
            texcoord = [values[0], values[1]]
            self.uvs.append(texcoord)
        remainder = dlen % 16
        if remainder > 0:
            padding_len = 16 - remainder
            file.read(padding_len)
        return file.tell()

    def print_info(self):
        print(f'[{self.name}] ---------------------------------------------')
        print(f'Offset          : 0x{self.d_offset:08X}')
        print(f'FCount          : {self.f_count} (ADDR: 0x{self.face_addr:X} MIN: {self.min_f_idx} MAX: {self.max_f_idx})')
        print(f'VCount          : {self.v_count}')
        print(f'Position Addr   : 0x{self.position_addr:X}')
        print(f'V.Normal Addr   : 0x{self.normal_addr:X}')
        print(f'V.Tangent Addr  : 0x{self.tangent_addr:X}')
        print(f'V.Binormal Addr : 0x{self.binormal_addr:X}')
        print(f'V.Weights Addr  : 0x{self.weights_addr:X}')
        print(f'V.BlendIdx Addr : 0x{self.blend_idx_addr:X} (MAX: {self.max_blend_idx})')
        print(f'V.Texcoord Addr : 0x{self.uv_addr:X}')
        print(f'EOF Addr        : 0x{self.eof_addr:X}')
        print(f'MeshParamSets   : ' + json.dumps(self.get_axe_json_data(), ensure_ascii=False, indent=4))

class MeshPaser:
    uint32_prefix       = 0
    base_offset         = 0
    mesh_count          = 0
    mesh_data_list      = []
    file_size           = 0
    file                = None
    
    def __init__(self, file, offset: int):
        self.base_offset = offset
        self.file = file
        # Get file size
        self.file.seek(0, os.SEEK_END)
        self.file_size = self.file.tell()
        self.file.seek(offset, os.SEEK_SET)
        # Read header
        data = self.file.read(0x30)
        if len(data) < 0x30:
            logger.error('Mesh data session size is too small')
            return
        values = struct.unpack('>12I', data)
        self.uint32_prefix = values[0]
        if self.uint32_prefix != 0x144C0000:
            return
        # Find mesh list
        self.mesh_count, ptr = self.__seek_mesh_heder_list__(values[10])
        if self.mesh_count == 0:
            return
        # Build mesh list
        self.mesh_data_list = self.__build_mesh_header_list__(ptr)
        for i in range(len(self.mesh_data_list)):
            self.mesh_data_list[i].start_paser(i, self.file)
        
    def __seek_mesh_heder_list__(self, offset: int) -> Tuple[int, int]:
        self.file.seek(self.base_offset + offset, os.SEEK_SET)
        data = self.file.read(8)
        if len(data) < 8:
            logger.error('Cannot seek mesh header list (-1)')
            return 0, 0
        # Find the number of mesh
        values = struct.unpack('>2I', data)
        mesh_count = values[1] >> 16
        # Seek & find mesh list pointer
        self.file.seek(self.base_offset + values[0], os.SEEK_SET)
        data = self.file.read(4)  
        if len(data) < 4:
            logger.error('Cannot seek mesh header list (-2)')
            return 0, 0
        ptr = struct.unpack('>I', data)[0] - 16
        if ptr >= self.file_size:
            logger.error('Invalid mesh list pointer')
            return 0, 0
        return mesh_count, ptr
        
    def __build_mesh_header_list__(self, offset: int) -> list[MeshData]:
        res = []
        mesh_count = 0
        pre_offset = 0
        self.file.seek(self.base_offset + offset, os.SEEK_SET)
        for i in range(self.mesh_count):
            b_indices = self.__build_mapping_bone_indices__()
            b_indices_count = len(b_indices)
            data = self.file.read(0x30)
            if len(data) < 0x30:
                logger.error(f'[idx={i:02}] Stop build mesh header list, caused by reading fail')
                return res
            values = struct.unpack('>12I', data)
            v_count = values[0] & 0xFFFF
            f_count = (values[0] >> 16) // 3
            d_offset = values[1]
            if d_offset <= pre_offset:
                logger.warning(f'[idx={i:02}] This mesh data offset is small than before, it could be parsed in the bad data session, skip ...')
                continue
            if d_offset == 0:
                logger.warning(f'[idx={i:02}] This mesh data offset is invalid, skip ...')
                continue
            if v_count == 0:
                logger.warning(f'[idx={i:02}] This mesh vertex count is invalid, skip ...')
                continue
            if f_count == 0:
                logger.warning(f'[idx={i:02}] This mesh face count is invalid, skip ...')
                continue
            if b_indices_count == 0:
                logger.warning(f'[idx={i:02}] No bone indices of this mesh, skip ...')
                continue
            logger.debug(f'[idx={i:02}] d_offset=0x{d_offset:08x} v_count={v_count} f_count={f_count} b_indices.size={b_indices_count}')
            res.append(MeshData(f'mesh_{d_offset:08x}', v_count, f_count, b_indices, self.base_offset + d_offset))
            pre_offset = d_offset
            mesh_count += 1
        if self.mesh_count != mesh_count:
            time.sleep(1.5)
        return res

    def __build_mapping_bone_indices__(self) -> list[int]:
        dlen = 0
        indices = []
        while True:
            data = self.file.read(4)
            dlen += len(data)
            if len(data) < 4:
                break
            slot = struct.unpack('>I', data)[0]
            if slot == 0:
                break
            count = slot & 0xFFFF
            beg_id = slot >> 16
            for i in range(count):
                indices.append(beg_id + i)
        remainder = dlen % 16
        if remainder > 0:
            padding_len = 16 - remainder
            self.file.read(padding_len)
        return indices
        
    def is_valid_data(self) -> bool:
        if self.uint32_prefix != 0x144C0000:
            logger.error(f'Mesh data session prefix is not correct (0x{self.uint32_prefix:08X})')
            return
        if self.mesh_count == 0:
            logger.error(f'Cannot estimate the number of mesh')
            return False
        return True
        
    def print_mesh_list(self):
        for mesh in self.mesh_data_list:
            print('')
            mesh.print_info()
        
#######################################################################################################
# Bones Paser

class BoneMatrix:
    float_tx1 = []
    float_tx2 = []
    float_tx3 = []
    float_tx4 = []
    float_xyz = []
    scale_xyz = []
    
    def __init__(self, values: list[int]):
        if len(values) < 16:
            logger.error('Bone matrix input list size is too small')
            return
        self.float_xyz = [ 0.0, 0.0, 0.0 ]
        self.float_tx1 = [ ReformValue.I2f(values[0]),  ReformValue.I2f(values[1]),  ReformValue.I2f(values[2]),  ReformValue.I2f(values[3])  ]
        self.float_tx2 = [ ReformValue.I2f(values[4]),  ReformValue.I2f(values[5]),  ReformValue.I2f(values[6]),  ReformValue.I2f(values[7])  ]
        self.float_tx3 = [ ReformValue.I2f(values[8]),  ReformValue.I2f(values[9]),  ReformValue.I2f(values[10]), ReformValue.I2f(values[11]) ]
        self.float_tx4 = [ ReformValue.I2f(values[12]), ReformValue.I2f(values[13]), ReformValue.I2f(values[14]), ReformValue.I2f(values[15]) ]
        self.scale_xyz = self.__build_scale_factor__()
        
    def __build_scale_factor__(self):
        return [math.sqrt((self.float_tx1[0] ** 2) + (self.float_tx2[0] ** 2) + (self.float_tx3[0] ** 2)),
                math.sqrt((self.float_tx1[1] ** 2) + (self.float_tx2[1] ** 2) + (self.float_tx3[1] ** 2)),
                math.sqrt((self.float_tx1[2] ** 2) + (self.float_tx2[2] ** 2) + (self.float_tx3[2] ** 2))]

    def get_parent_matrix(self):
        return [    [ self.float_tx1[0], self.float_tx1[1], self.float_tx1[2], 0.0 ], 
                    [ self.float_tx2[0], self.float_tx2[1], self.float_tx2[2], 0.0 ],
                    [ self.float_tx3[0], self.float_tx3[1], self.float_tx3[2], 0.0 ],
                    [ 0.0, 0.0, 0.0, 1.0 ]  ]
                    
    def get_current_matrix(self):
        return [    [ 1.0, 0.0, 0.0, -self.float_tx4[0] ], 
                    [ 0.0, 1.0, 0.0, -self.float_tx4[1] ],
                    [ 0.0, 0.0, 1.0, -self.float_tx4[2] ],
                    [ 0.0, 0.0, 0.0, 1.0 ]  ]

    def set_xyz_float(self, values: list[int]):
        if len(values) < 3:
            return
        self.float_xyz[0] = ReformValue.I2f(values[0])
        self.float_xyz[1] = ReformValue.I2f(values[1])
        self.float_xyz[2] = ReformValue.I2f(values[2])
        
    def print(self, b_show_xyz_only=True):
        if not b_show_xyz_only:
            print('TX1 :', format(self.float_tx1[0], '.4f') + ',', format(self.float_tx1[1], '.4f') + ',', format(self.float_tx1[2], '.4f') + ',', format(self.float_tx1[3], '.4f'))
            print('TX2 :', format(self.float_tx2[0], '.4f') + ',', format(self.float_tx2[1], '.4f') + ',', format(self.float_tx2[2], '.4f') + ',', format(self.float_tx2[3], '.4f'))
            print('TX3 :', format(self.float_tx3[0], '.4f') + ',', format(self.float_tx3[1], '.4f') + ',', format(self.float_tx3[2], '.4f') + ',', format(self.float_tx3[3], '.4f'))
            print('TX4 :', format(self.float_tx4[0], '.4f') + ',', format(self.float_tx4[1], '.4f') + ',', format(self.float_tx4[2], '.4f') + ',', format(self.float_tx4[3], '.4f'))
        print('VAL :', format(self.float_xyz[0], '.4f') + ',', format(self.float_xyz[1], '.4f') + ',', format(self.float_xyz[2], '.4f'))
        
class BoneData:
    id          = 0
    index       = 0
    name        = '' 
    parent_idx  = -1
    matrix      = None
    translation = []
    
    def __init__(self, index: int, id: int, name: str, matrix: BoneMatrix):
        self.id = id
        self.index = index
        self.name = name
        self.matrix = matrix
        self.translation = [ self.matrix.float_xyz[0], self.matrix.float_xyz[1], self.matrix.float_xyz[2] ]
        
    def update_translation(self, x: int, y: int, z: int):
        self.translation[0] = x
        self.translation[1] = y
        self.translation[2] = z
        
    def get_axe_json_data(self, mask=False):
        if not mask:
            node_name = self.name
            translation = [ self.translation[0], self.translation[1], self.translation[2] ]
            parent_idx = self.parent_idx
        else:
            node_name = f'unused_bone_{self.index}'
            translation = [ 0.0, 0.0, 0.0 ]
            parent_idx = -1
        return {
            "NodeName"      : node_name,
            "NodeIndex"     : self.index,
            "ParentIndex"   : parent_idx,
            "Translation"   : translation
        }
        
# ------------------------------------------------------------------------------------
def build_hierarchy(bones):
    """建立父子關係映射表和錯誤節點列表"""
    tree = defaultdict(list)
    error_nodes = []
    root_indices = []
    for idx, bone in enumerate(bones):
        if bone.parent_idx == -1:
            root_indices.append(idx)
        else:
            if 0 <= bone.parent_idx < len(bones):
                tree[bone.parent_idx].append(idx)
            else:
                error_nodes.append(idx)
    return tree, root_indices, error_nodes

def print_tree(node_idx, bones, tree, prefix='', is_last=True):
    """遞歸打印樹狀結構"""
    bone = bones[node_idx]
    # 當前節點顯示
    connector = "└── " if is_last else "├── "
    print(f"{prefix}{connector}{bone.name}")
    # 子節點處理
    children = tree.get(node_idx, [])
    for i, child_idx in enumerate(children):
        is_last_child = i == len(children) - 1
        new_prefix = prefix + ("    " if is_last else "│   ")
        print_tree(child_idx, bones, tree, new_prefix, is_last_child)

def print_bone_tree(bones):
    """主打印函數"""
    tree, roots, errors = build_hierarchy(bones)
    # 打印正常結構
    for i, root_idx in enumerate(roots):
        bone = bones[root_idx]
        print(f"{bone.name}")
        children = tree.get(root_idx, [])
        for j, child_idx in enumerate(children):
            is_last = j == len(children) - 1
            print_tree(child_idx, bones, tree, "", is_last)
    # 打印錯誤節點
    if errors:
        print("\n[Invalid Node]")
        for err_idx in errors:
            bone = bones[err_idx]
            print(f"└── {bone.name} (Invalid parent index: {bone.parent_idx})")
# ------------------------------------------------------------------------------------

class BonesPaser:
    uint32_prefix       = 0
    base_offset         = 0
    bones_matrix_ptr    = 0
    bones_num           = 0
    bone_data_list      = []
    file_size           = 0
    file                = None
    
    def __init__(self, file, offset: int):
        self.base_offset = offset
        self.file = file
        # Get file size
        self.file.seek(0, os.SEEK_END)
        self.file_size = self.file.tell()
        self.file.seek(offset, os.SEEK_SET)
        # Read header
        data = self.file.read(0x30)
        if len(data) < 0x28:
            logger.error('Bones data session size is too small')
            return
        values = struct.unpack('>12I', data)
        self.uint32_prefix = values[0]
        if self.uint32_prefix != 0x17030000:
            return
        # Seek to the bone matrix
        self.bones_matrix_ptr = self.__seek_bone_matrix__()
         # Check my theory is correct
        if self.bones_matrix_ptr != values[4] + self.base_offset:
            self.bones_matrix_ptr = 0
            logger.error('Bones matrix pointer is not correct in header in theory')
        if self.bones_matrix_ptr == 0:
            return
        # Start to estimate the number of bones and get matrix list
        matrixs = self.__build_bone_matrix__()
        self.bones_num = len(matrixs)
        if self.bones_num == 0:
            return
        # Start build bone list
        self.bone_data_list = self.__build_bone_list__(matrixs)
        # Start calculate bone translation
        for bone in self.bone_data_list:
            self.__update_bones_translation__(bone)

    def __seek_bone_matrix__(self) -> int:
        beg = self.file.tell()
        seek_result = 0
        history = []
        while True:
            data = self.file.read(16)
            if len(data) < 16:
                break
            values = struct.unpack('>4I', data)
            history.append(values[3])
            if len(history) > 4:
                history.pop(0)
            if values[3] == 0x3F800000:
                # double check this matrix is what I need
                if len(history) == 4 and history[0] == 0 and history[1] == 0 and history[2] == 0:
                    pos = self.file.tell()
                    if pos > 0x40:
                        seek_result = pos - 0x40
                    break
        if seek_result > 0:
            self.file.seek(seek_result, os.SEEK_SET)
            return seek_result
        # Move back to the beginning (for fail to seek matrix case)
        self.file.seek(beg, os.SEEK_SET)
        return 0
        
    def __build_bone_matrix__(self) -> list[BoneMatrix]:
        beg = self.file.tell()
        res = []
        while True:
            data = self.file.read(16 * 4)
            if len(data) < 16 * 4:
                return []
            values = struct.unpack('>16I', data)
            if values[3] == 0 and values[7] == 0 and values[11] == 0 and values[15] == 0x3F800000:
                res.append(BoneMatrix(values))
                continue
            break
        # Move back to the beginning of matrix
        self.file.seek(beg, os.SEEK_SET)
        return res
        
    def __build_bone_list__(self, matrixs: list[BoneMatrix]) -> list[BoneData]:
        self.file.seek(self.base_offset + 0x28, os.SEEK_SET)
        res = []
        for i in range(self.bones_num):
            data = self.file.read(0x1C)
            if len(data) < 0x1C:
                logger.error('Bones table size is too small')
                return
            values = struct.unpack('>7I', data)
            # Read the name of bone
            bone_name = self.__read_bone_name__(values[6])
            # Read bone ID
            bone_id = values[3] >> 16
            # Find parent index
            parent_idx = self.__find_parent_index__(values[4])
            # Push to list
            obj = BoneData(i, bone_id, bone_name, matrixs[i])
            obj.matrix.set_xyz_float([values[0], values[1], values[2]])
            obj.parent_idx = parent_idx
            res.append(obj)
        return res
        
    def __update_bones_translation__(self, target: BoneData):
        mt = self.__matrix_multiply__(target.matrix.get_parent_matrix(), target.matrix.get_current_matrix())
        target.update_translation(mt[0][3], mt[1][3], mt[2][3])
        
    def __find_parent_index__(self, offset: int) -> Tuple[int, str]:
        tmp_offset = self.file.tell()
        if offset == 0:
            return -1
        self.file.seek(self.base_offset + offset, os.SEEK_SET)
        data = self.file.read(0x1C)
        if len(data) < 0x1C:
            logger.warning('Cannot find parent bone, table size is too small')
            self.file.seek(tmp_offset, os.SEEK_SET)
            return -1
        values = struct.unpack('>7I', data)
        # Read the name of bone
        bone_name = self.__read_bone_name__(values[6])
        # Read bone ID
        bone_cur = values[3] >> 16
        if bone_cur < 0 or bone_cur >= self.bones_num:
            self.file.seek(tmp_offset, os.SEEK_SET)
            return -1
        self.file.seek(tmp_offset, os.SEEK_SET)
        return bone_cur

    def __read_bone_name__(self, offset: int) -> str:
        tmp_offset = self.file.tell()
        self.file.seek(self.base_offset + offset, os.SEEK_SET)
        bone_name = BinStreamReader.read_string(self.file)
        self.file.seek(tmp_offset, os.SEEK_SET)
        return bone_name
        
    def __matrix_multiply__(self, a, b):
        return [
            [
                sum(a[i][k] * b[k][j] for k in range(len(b)))
                for j in range(len(b[0]))
            ]
            for i in range(len(a))
        ]
 
    def is_valid_data(self) -> bool:
        if self.uint32_prefix != 0x17030000:
            logger.error(f'Bones data session prefix is not correct (0x{self.uint32_prefix:08X})')
            return
        if self.bones_matrix_ptr == 0:
            logger.error(f'Cannot locate matrix of bones')
            return False
        if self.bones_num == 0:
            logger.error(f'Cannot estimate the number of bones')
            return False
        return True
        
    def print_bone_list(self):
        for bone in self.bone_data_list:
            print('')
            print(bone.name)
            bone.matrix.print(False)
            
    def draw_bone_tree(self):
        print_bone_tree(self.bone_data_list)
            
#######################################################################################################
# AXE Packer

def axe_packer(filename: str, m: MeshPaser, b: BonesPaser, reverse=False, rename=False, skip=0, split=False):
    output_plc = filename + '.plc'
    shared_source = os.path.basename(filename)
    exclude_bone_indices = []
    mesh_param_sets = []
    bone_node_list = []
    mesh_count = 0 if m is None else len(m.mesh_data_list)
    bone_count = 0 if b is None else len(b.bone_data_list)
    # Build mesh param sets -----------------------------------------------------------------------
    for pos in range(mesh_count):
        i = pos if not reverse else mesh_count - 1 - pos
        # Skip the first N meshes
        if skip > 0:
            exclude_bone_indices.extend(m.mesh_data_list[i].bone_indices)
            skip -= 1
            continue
        # Rename mesh by name of bone
        if rename and len(m.mesh_data_list[i].bone_indices) > 0:
            b_idx = m.mesh_data_list[i].bone_indices[0]
            if b_idx < bone_count:
                new_name = 'mesh_' + b.bone_data_list[b_idx].name.lower().replace(' ', '_')
                m.mesh_data_list[i].name = new_name
        # Get JSON AXE data 
        param = m.mesh_data_list[i].get_axe_json_data()
        mesh_param_sets.append(param) 
    # Build bone node list ------------------------------------------------------------------------
    for pos in range(bone_count):
        mask = pos in exclude_bone_indices
        if mask:
            parent_idx = b.bone_data_list[pos].parent_idx
            if parent_idx > 0:
                exclude_bone_indices.append(parent_idx)
        param = b.bone_data_list[pos].get_axe_json_data(pos in exclude_bone_indices)
        bone_node_list.append(param)
    # Create AXE content --------------------------------------------------------------------------
    for i in range(len(mesh_param_sets)):
        mesh_count = 1 if split else len(mesh_param_sets)
        param_sets = [ mesh_param_sets[i] ] if split else mesh_param_sets
        data = {
            "Document"      : "Advanced Mesh Reaper Parameter List Container",
            "Version"       : 102,
            "Endianness"    : "Big",
            "SharedSource"  : shared_source,
            "MeshCount"     : mesh_count,
            "MeshParamSets" : param_sets,
            "BoneCount"     : bone_count,
            "BoneNodeList"  : bone_node_list
        }
        if split:
            output_plc = filename + f'.{i + 1:02}.plc'
        txt = json.dumps(data, ensure_ascii=False, indent=4)
        with open(output_plc, "w", encoding="utf-8") as file:
            file.write(txt)
#           print(txt)
        if not split:
            break

#######################################################################################################
# PAK Parser

def pak_parser(filename: str, mesh_manual_offset: int, bone_manual_offset: int) -> Tuple[MeshPaser, BonesPaser]:
    uint32_mesh_ptr = 0x00
    uint32_bone_ptr = 0x00
    with open(filename, 'rb') as f:
        # Manual section part
        if mesh_manual_offset != 0:
            uint32_mesh_ptr = mesh_manual_offset
        if bone_manual_offset != 0:
            uint32_bone_ptr = bone_manual_offset
        # Auto section part
        if uint32_mesh_ptr == 0 and uint32_bone_ptr == 0:
            # Parse *.pak header
            pak = PakHeader(f)
            if not pak.is_mesh_pak():
                logger.warning(f'You may need to set mesh & bone data section offset for this PAK manually. (For example: -p "{filename}" -m d75570 -b dc1770)')
                print('[HINT] Mesh data section start with 0x144C0000 for prefix. (Try to use HxD Hex Editor to find it by yourself)')
                print('[HINT] Bone data section start with 0x17030000 for prefix. (Try to use HxD Hex Editor to find it by yourself)')
                return None, None
            logger.debug(f'[Offset] Entry Table  : 0x{pak.uint32_entry_ptr:08X}')
            # Parse entry pointers
            entry = EntryPointer(f, pak.uint32_entry_ptr)
            if not entry.is_valid_data():
                return None, None
            uint32_mesh_ptr = entry.uint32_mesh_ptr
            uint32_bone_ptr = entry.uint32_bone_ptr
        # Print section result
        logger.debug(f'[Offset] Mesh Section : 0x{uint32_mesh_ptr:08X}')
        logger.debug(f'[Offset] Bone Section : 0x{uint32_bone_ptr:08X}')
        # Mesh parser
        meshs = MeshPaser(f, uint32_mesh_ptr)
        if not meshs.is_valid_data():
            return None, None
        meshs.print_mesh_list()
        # Bones paser
        bones = BonesPaser(f, uint32_bone_ptr)
        if not bones.is_valid_data():
            logger.warning('Cannot export bone information')
            return meshs, None
        logger.debug(f'[Offset] Bone Matrix  : 0x{bones.bones_matrix_ptr:08X}')
        logger.debug(f'Bones Number          : 0x{bones.bones_num:08X} ({bones.bones_num})')
        bones.print_bone_list()
        bones.draw_bone_tree()
        return meshs, bones

#######################################################################################################
# Main
        
async def main(args):
    # Check *.pak exists
    if not os.path.exists(args.pak):
        logger.error(f'{args.pak} is not found')
        return
    # Start parse PAK
    bone_manual_offset = int(args.bone, 16)
    mesh_manual_offset = int(args.mesh, 16)
    meshs, bones = pak_parser(args.pak, mesh_manual_offset, bone_manual_offset)
    # Output as *.plc for AXE
    axe_packer(args.pak, meshs, bones, args.reverse, args.rename, args.skip, args.split)

def args_parser():
    parser = argparse.ArgumentParser(description='Invizimals PAK Mesh Finder')
    parser.add_argument('-p', '--pak', type=str, required=True, help='Give a *.pak file for creating AXE(*.plc) content')
    parser.add_argument('-m', '--mesh', type=str, required=False, default='0', help='Set the HEX offset of mesh data section manually (default: auto)')
    parser.add_argument('-b', '--bone', type=str, required=False, default='0', help='Set the HEX offset of bone data section manually (default: auto)')
    parser.add_argument('-s', '--skip', type=int, required=False, default=0, help='Skip the first N meshes (default: 0)')
    parser.add_argument('-r', '--reverse', action='store_true', default=False, help='Reverse the order of the mesh list (default: OFF)')
    parser.add_argument('-a', '--rename', action='store_true', default=False, help='Rename the mesh with bone indices (default: OFF)')
    parser.add_argument('-t', '--split', action='store_true', default=False, help='Split different meshs to different plc files (default: OFF)')
    return parser.parse_args()

if __name__ == "__main__":
    args = args_parser()
    asyncio.run(main(args))