# Copyright Vertex.AI

from __future__ import print_function

import contextlib
import ctypes
import hashlib
import logging
import numpy as np
import os
import pkg_resources
import plaidml.context
import plaidml.exceptions
import plaidml.library
import platform
import threading
import traceback
import weakref

from collections import namedtuple
from itertools import islice

if 'PLAIDML_EXPERIMENTAL_CONFIG' not in os.environ:
    os.environ['PLAIDML_EXPERIMENTAL_CONFIG'] = os.path.join(
        pkg_resources.resource_filename('plaidml', 'experimental.json'))

if 'PLAIDML_DEFAULT_CONFIG' not in os.environ:
    os.environ['PLAIDML_DEFAULT_CONFIG'] = os.path.join(
        pkg_resources.resource_filename('plaidml', 'config.json'))


# Create types for all PlaidML structures, so that we can get some type checking.
class _C_Devconf(ctypes.Structure):
    pass


class _C_Device(ctypes.Structure):
    pass


class _C_DeviceEnumerator(ctypes.Structure):
    pass


class _C_Buffer(ctypes.Structure):
    pass


class _C_Mapping(ctypes.Structure):
    pass


class _C_Shape(ctypes.Structure):
    pass


class _C_Function(ctypes.Structure):
    pass


class _C_Var(ctypes.Structure):
    pass


class _C_Composer(ctypes.Structure):
    pass


class _C_Applier(ctypes.Structure):
    pass


class _C_Invoker(ctypes.Structure):
    pass


class _C_Invocation(ctypes.Structure):
    pass


class _C_Gradient(ctypes.Structure):
    pass


_ENUM_DEVICES_FUNCTYPE = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                          ctypes.POINTER(_C_DeviceEnumerator))
_MAP_BUFFER_FUNCTYPE = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(_C_Mapping))

DEFAULT_LOG_HANDLER = logging.StreamHandler()
"""The default logging handler, provided as a global so that modules
   using this one can remove it from the module logger if desired."""

DEFAULT_LOG_HANDLER.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
DEFAULT_LOG_HANDLER.setLevel(logging.INFO)


class _Library(plaidml.library.Library):

    def __init__(self, logger=None):

        if not logger:
            plog = logging.getLogger(__name__)
            plog.setLevel(logging.INFO)
            plog.addHandler(DEFAULT_LOG_HANDLER)
            logger = plog.log

        if platform.system() == 'Windows':
            libname = 'plaidml.dll'
        else:
            libname = 'libplaidml.so'
        libpath = pkg_resources.resource_filename(__name__, libname)
        lib = ctypes.cdll.LoadLibrary(libpath)

        super(_Library, self).__init__(lib, logger=logger)

        # PLAIDML_API bool plaidml_query_devconf(
        #   vai_ctx* ctx,
        #   plaidml_devconf* devconf,
        #   plaidml_device_property property,
        #   void* output_buffer,
        #   size_t output_buffer_size,
        #   size_t* output_buffer_size_required
        # );
        self.plaidml_query_devconf = lib.plaidml_query_devconf
        self.plaidml_query_devconf.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_Devconf),  # plaidml_devconf* devconf
            ctypes.c_int,  # plaidml_device_property property
            ctypes.c_void_p,  # void* output_buffer
            ctypes.c_size_t,  # size_t output_buffer_size
            ctypes.POINTER(ctypes.c_size_t)  # size_t* output_buffer_size_required
        ]
        self.plaidml_query_devconf.restype = ctypes.c_bool
        self.plaidml_query_devconf.errcheck = self._check_err

        # PLAIDML_API plaidml_device* plaidml_open_device(vai_ctx* ctx, plaidml_devconf* devconf);
        self.plaidml_open_device = lib.plaidml_open_device
        self.plaidml_open_device.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),
            ctypes.POINTER(_C_Devconf)  # plaidml_devconf* devconf
        ]
        self.plaidml_open_device.restype = ctypes.POINTER(_C_Device)
        self.plaidml_open_device.errcheck = self._check_err

        # PLAIDML_API void plaidml_close_device(plaidml_device* device);
        self.plaidml_close_device = lib.plaidml_close_device
        self.plaidml_close_device.argypes = [
            ctypes.POINTER(_C_Device)  # plaidml_device* device
        ]

        # PLAIDML_API plaidml_device_enumerator* plaidml_alloc_device_enumerator(
        #   vai_ctx* ctx,
        #   const char* configuration,
        #   void (*callback)(void* arg, plaidml_device_enumerator* enumerator),
        #   void* arg
        # );
        self.plaidml_alloc_device_enumerator = lib.plaidml_alloc_device_enumerator
        self.plaidml_alloc_device_enumerator.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            _ENUM_DEVICES_FUNCTYPE,  # void (*callback)(void* arg, plaidml_device_enumerator* enumerator)
            ctypes.c_void_p  # void* arg
        ]
        self.plaidml_alloc_device_enumerator.restype = ctypes.POINTER(_C_DeviceEnumerator)
        self.plaidml_alloc_device_enumerator.errcheck = self._check_err

        # PLAIDML_API plaidml_device_enumerator* plaidml_alloc_device_enumerator_with_config(
        #   vai_ctx* ctx,
        #   const char* configuration,
        #   void (*callback)(void* arg, plaidml_device_enumerator* enumerator),
        #   void* arg
        # );
        self.plaidml_alloc_device_enumerator_with_config = lib.plaidml_alloc_device_enumerator_with_config
        self.plaidml_alloc_device_enumerator_with_config.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.c_char_p,  # const char* configuration
            _ENUM_DEVICES_FUNCTYPE,  # void (*callback)(void* arg, plaidml_device_enumerator* enumerator)
            ctypes.c_void_p  # void* arg
        ]
        self.plaidml_alloc_device_enumerator_with_config.restype = ctypes.POINTER(
            _C_DeviceEnumerator)
        self.plaidml_alloc_device_enumerator_with_config.errcheck = self._check_err

        # PLAIDML_API void plaidml_free_device_enumerator(plaidml_device_enumerator* enumerator);
        self.plaidml_free_device_enumerator = lib.plaidml_free_device_enumerator
        self.plaidml_free_device_enumerator.argtypes = [
            ctypes.POINTER(_C_DeviceEnumerator)  # plaidml_device_enumerator* enumerator
        ]

        # PLAIDML_API plaidml_devconf* plaidml_get_devconf(vai_ctx* ctx, plaidml_device_enumerator* enumerator, size_t index);
        self.plaidml_get_devconf = lib.plaidml_get_devconf
        self.plaidml_get_devconf.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_DeviceEnumerator),  # plaidml_device_enumerator* enumerator
            ctypes.c_size_t  # size_t index
        ]
        self.plaidml_get_devconf.restype = ctypes.POINTER(_C_Devconf)
        self.plaidml_get_devconf.errcheck = self._check_err

        # PLAIDML_API plaidml_buffer* plaidml_alloc_buffer(vai_ctx* ctx, plaidml_device* device, uint64_t size);
        self.plaidml_alloc_buffer = lib.plaidml_alloc_buffer
        self.plaidml_alloc_buffer.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_Device),  # plaidml_device* device
            ctypes.c_uint64  # uint64_t size
        ]
        self.plaidml_alloc_buffer.restype = ctypes.POINTER(_C_Buffer)
        self.plaidml_alloc_buffer.errcheck = self._check_err

        # PLAIDML_API void plaidml_free_buffer(plaidml_buffer* buffer);
        self.plaidml_free_buffer = lib.plaidml_free_buffer
        self.plaidml_free_buffer.argtypes = [
            ctypes.POINTER(_C_Buffer)  # plaidml_buffer* buffer
        ]

        # PLAIDML_API plaidml_mapping* plaidml_map_buffer_current(vai_ctx* ctx,
        #   plaidml_buffer* buffer,
        #   void (*callback)(void* arg, plaidml_mapping* mapping),
        #   void* arg
        # );
        self.plaidml_map_buffer_current = lib.plaidml_map_buffer_current
        self.plaidml_map_buffer_current.argtypes = [
            ctypes.POINTER(_C_Buffer),  # plaidml_buffer* buffer
            _MAP_BUFFER_FUNCTYPE,  # void (*callback)(void* arg, plaidml_mapping* mapping)
            ctypes.c_void_p  # void* arg
        ]
        self.plaidml_map_buffer_current.restype = ctypes.POINTER(_C_Mapping)
        self.plaidml_map_buffer_current.errcheck = self._check_err

        # PLAIDML_API plaidml_mapping* plaidml_map_buffer_discard(vai_ctx* ctx, plaidml_buffer* buffer);
        self.plaidml_map_buffer_discard = lib.plaidml_map_buffer_discard
        self.plaidml_map_buffer_discard.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_Buffer)  # plaidml_buffer* buffer
        ]
        self.plaidml_map_buffer_discard.restype = ctypes.POINTER(_C_Mapping)
        self.plaidml_map_buffer_discard.errcheck = self._check_err

        # PLAIDML_API char* plaidml_get_mapping_base(vai_ctx* ctx, plaidml_mapping* mapping);
        self.plaidml_get_mapping_base = lib.plaidml_get_mapping_base
        self.plaidml_get_mapping_base.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_Mapping)  # plaidml_mapping* mapping
        ]
        self.plaidml_get_mapping_base.restype = ctypes.c_void_p
        self.plaidml_get_mapping_base.errcheck = self._check_err

        # PLAIDML_API size_t plaidml_get_mapping_size(vai_ctx* ctx, plaidml_mapping* mapping);
        self.plaidml_get_mapping_size = lib.plaidml_get_mapping_size
        self.plaidml_get_mapping_size.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_Mapping)  # plaidml_mapping* mapping
        ]
        self.plaidml_get_mapping_size.restype = ctypes.c_size_t
        self.plaidml_get_mapping_size.errcheck = self._check_err

        # PLAIDML_API bool plaidml_writeback_mapping(vai_ctx* ctx, plaidml_mapping* mapping);
        self.plaidml_writeback_mapping = lib.plaidml_writeback_mapping
        self.plaidml_writeback_mapping.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_Mapping)  # plaidml_mapping* mapping
        ]
        self.plaidml_writeback_mapping.restype = ctypes.c_bool
        self.plaidml_writeback_mapping.errcheck = self._check_err

        # PLAIDML_API void plaidml_free_mapping(plaidml_mapping* mapping);
        self.plaidml_free_mapping = lib.plaidml_free_mapping
        self.plaidml_free_mapping.argtypes = [
            ctypes.POINTER(_C_Mapping)  # plaidml_mapping* mapping
        ]

        # PLAIDML_API plaidml_shape* plaidml_alloc_shape(vai_ctx* ctx, plaidml_datatype datatype);
        self.plaidml_alloc_shape = lib.plaidml_alloc_shape
        self.plaidml_alloc_shape.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.c_int  # plaidml_datatype datatype
        ]
        self.plaidml_alloc_shape.restype = ctypes.POINTER(_C_Shape)
        self.plaidml_alloc_shape.errcheck = self._check_err

        # PLAIDML_API void plaidml_free_shape(plaidml_shape* shape);
        self.plaidml_free_shape = lib.plaidml_free_shape
        self.plaidml_free_shape.argtypes = [
            ctypes.POINTER(_C_Shape)  # plaidml_shape* shape
        ]

        # PLAIDML_API bool plaidml_set_shape_offset(vai_ctx* ctx, plaidml_shape* shape, uint64_t offset_in_elements);
        self.plaidml_set_shape_offset = lib.plaidml_set_shape_offset
        self.plaidml_set_shape_offset.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_Shape),  # plaidml_shape* shape
            ctypes.c_uint64  # uint64_t offset_in_elements
        ]
        self.plaidml_set_shape_offset.restype = ctypes.c_bool
        self.plaidml_set_shape_offset.errcheck = self._check_err

        # PLAIDML_API bool plaidml_add_dimension(
        #   vai_ctx* ctx,
        #   plaidml_shape* shape,
        #   uint64_t size_in_elements,
        #   int64_t stride_in_elements
        # );
        self.plaidml_add_dimension = lib.plaidml_add_dimension
        self.plaidml_add_dimension.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_Shape),  # plaidml_shape* shape
            ctypes.c_uint64,  # uint64_t size_in_elements
            ctypes.c_int64  # int64_t stride_in_elements
        ]
        self.plaidml_add_dimension.restype = ctypes.c_bool
        self.plaidml_add_dimension.errcheck = self._check_err

        # PLAIDML_API plaidml_datatype plaidml_get_shape_type(plaidml_shape* shape);
        self.plaidml_get_shape_type = lib.plaidml_get_shape_type
        self.plaidml_get_shape_type.argtypes = [
            ctypes.POINTER(_C_Shape)  # plaidml_shape* shape
        ]
        self.plaidml_get_shape_type.restype = ctypes.c_int
        self.plaidml_get_shape_type.errcheck = self._check_err

        # PLAIDML_API uint64_t plaidml_get_shape_offset(plaidml_shape* shape);
        self.plaidml_get_shape_offset = lib.plaidml_get_shape_offset
        self.plaidml_get_shape_offset.argtypes = [
            ctypes.POINTER(_C_Shape)  # plaidml_shape* shape
        ]
        self.plaidml_get_shape_offset.restype = ctypes.c_uint64

        # PLAIDML_API size_t plaidml_get_shape_dimension_count(plaidml_shape* shape);
        self.plaidml_get_shape_dimension_count = lib.plaidml_get_shape_dimension_count
        self.plaidml_get_shape_dimension_count.argtypes = [
            ctypes.POINTER(_C_Shape)  # plaidml_shape* shape
        ]
        self.plaidml_get_shape_dimension_count.restype = ctypes.c_size_t

        # PLAIDML_API uint64_t plaidml_get_shape_dimension_size(plaidml_shape* shape, size_t dim);
        self.plaidml_get_shape_dimension_size = lib.plaidml_get_shape_dimension_size
        self.plaidml_get_shape_dimension_size.argtypes = [
            ctypes.POINTER(_C_Shape),  # plaidml_shape* shape
            ctypes.c_size_t  # size_t dim
        ]
        self.plaidml_get_shape_dimension_size.restype = ctypes.c_uint64
        self.plaidml_get_shape_dimension_size.errcheck = self._check_err

        # PLAIDML_API int64_t plaidml_get_shape_dimension_stride(plaidml_shape* shape, size_t dim);
        self.plaidml_get_shape_dimension_stride = lib.plaidml_get_shape_dimension_stride
        self.plaidml_get_shape_dimension_stride.argtypes = [
            ctypes.POINTER(_C_Shape),  # plaidml_shape* shape
            ctypes.c_size_t  # size_t dim
        ]
        self.plaidml_get_shape_dimension_stride.restype = ctypes.c_int64
        self.plaidml_get_shape_dimension_stride.errcheck = self._check_err

        # PLAIDML_API uint64_t plaidml_get_shape_buffer_size(plaidml_shape* shape);
        self.plaidml_get_shape_buffer_size = lib.plaidml_get_shape_buffer_size
        self.plaidml_get_shape_buffer_size.argtypes = [
            ctypes.POINTER(_C_Shape)  # plaidml_shape* shape
        ]
        self.plaidml_get_shape_buffer_size.restype = ctypes.c_uint64

        # PLAIDML_API uint64_t plaidml_get_shape_element_count(plaidml_shape* shape);
        self.plaidml_get_shape_element_count = lib.plaidml_get_shape_element_count
        self.plaidml_get_shape_element_count.argtypes = [
            ctypes.POINTER(_C_Shape)  # plaidml_shape* shape
        ]
        self.plaidml_get_shape_element_count.restype = ctypes.c_uint64

        # PLAIDML_API void plaidml_free_function(plaidml_function* function);
        self.plaidml_free_function = lib.plaidml_free_function
        self.plaidml_free_function.argtypes = [
            ctypes.POINTER(_C_Function)  # plaidml_function* function
        ]

        # TODO: PLAIDML_API size_t plaidml_get_function_input_count(plaidml_function* function);
        # TODO: PLAIDML_API const char* plaidml_get_function_input(plaidml_function* function, size_t i);
        # TODO: PLAIDML_API size_t plaidml_get_function_output_count(plaidml_function* function);
        # TODO: PLAIDML_API const char* plaidml_get_function_output(plaidml_function* function, size_t i);

        # PLAIDML_API void plaidml_free_var(plaidml_var* var);
        self.plaidml_free_var = lib.plaidml_free_var
        self.plaidml_free_var.argtypes = [
            ctypes.POINTER(_C_Var)  # plaidml_var* var
        ]

        # PLAIDML_API plaidml_var* plaidml_alloc_placeholder(size_t num_dimensions);
        self.plaidml_alloc_placeholder = lib.plaidml_alloc_placeholder
        self.plaidml_alloc_placeholder.argtypes = [
            ctypes.c_size_t  # size_t num_dimensions
        ]
        self.plaidml_alloc_placeholder.restype = ctypes.POINTER(_C_Var)
        self.plaidml_alloc_placeholder.errcheck = self._check_err

        # PLAIDML_API plaidml_var* plaidml_alloc_int64(int64_t value);
        self.plaidml_alloc_int64 = lib.plaidml_alloc_int64
        self.plaidml_alloc_int64.argtypes = [
            ctypes.c_int64  # int64_t value
        ]
        self.plaidml_alloc_int64.restype = ctypes.POINTER(_C_Var)
        self.plaidml_alloc_int64.errcheck = self._check_err

        # PLAIDML_API plaidml_var* plaidml_alloc_real(double value);
        self.plaidml_alloc_real = lib.plaidml_alloc_real
        self.plaidml_alloc_real.argtypes = [
            ctypes.c_double  # double value
        ]
        self.plaidml_alloc_real.restype = ctypes.POINTER(_C_Var)
        self.plaidml_alloc_real.errcheck = self._check_err

        # PLAIDML_API plaidml_var* plaidml_alloc_tensor(vai_ctx* ctx, plaidml_buffer* buffer, plaidml_shape* shape);
        self.plaidml_alloc_tensor = lib.plaidml_alloc_tensor
        self.plaidml_alloc_tensor.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_Buffer),  # plaidml_buffer* buffer
            ctypes.POINTER(_C_Shape)  # plaidml_shape* shape
        ]
        self.plaidml_alloc_tensor.restype = ctypes.POINTER(_C_Var)
        self.plaidml_alloc_tensor.errcheck = self._check_err

        # PLAIDML_API plaidml_function* plaidml_build_coded_function(const char* code);
        self.plaidml_build_coded_function = lib.plaidml_build_coded_function
        self.plaidml_build_coded_function.argtypes = [
            ctypes.c_char_p,  # const char* code
            ctypes.c_char_p   # const char* id
        ]
        self.plaidml_build_coded_function.restype = ctypes.POINTER(_C_Function)
        self.plaidml_build_coded_function.errcheck = self._check_err

        # TODO: PLAIDML_API plaidml_function* plaidml_load_function(plaidml_device* dev, const char* file);

        # PLAIDML_API bool plaidml_save_function(plaidml_function* func, const char* file);
        self.plaidml_save_function = lib.plaidml_save_function
        self.plaidml_save_function.argtypes = [
            ctypes.POINTER(_C_Function),  # plaidml_function* func
            ctypes.c_char_p,  # const char* file
        ]
        self.plaidml_save_function.restype = ctypes.c_bool
        self.plaidml_save_function.errcheck = self._check_err

        # PLAIDML_API plaidml_composer* plaidml_alloc_composer();
        self.plaidml_alloc_composer = lib.plaidml_alloc_composer
        self.plaidml_alloc_composer.argtypes = []
        self.plaidml_alloc_composer.restype = ctypes.POINTER(_C_Composer)
        self.plaidml_alloc_composer.errcheck = self._check_err

        # PLAIDML_API bool plaidml_add_composer_input(plaidml_composer* composer, const char* name, plaidml_var* var);
        self.plaidml_add_composer_input = lib.plaidml_add_composer_input
        self.plaidml_add_composer_input.argtypes = [
            ctypes.POINTER(_C_Composer),  # plaidml_composer* composer
            ctypes.c_char_p,  # const char* name
            ctypes.POINTER(_C_Var)  # plaidml_var* var
        ]
        self.plaidml_add_composer_input.restype = ctypes.c_bool
        self.plaidml_add_composer_input.errcheck = self._check_err

        # PLAIDML_API bool plaidml_add_composer_output(plaidml_composer* composer, const char* name, plaidml_var* var);
        self.plaidml_add_composer_output = lib.plaidml_add_composer_output
        self.plaidml_add_composer_output.argtypes = [
            ctypes.POINTER(_C_Composer),  # plaidml_composer* composer
            ctypes.c_char_p,  # const char* name
            ctypes.POINTER(_C_Var)  # plaidml_var* var
        ]
        self.plaidml_add_composer_output.restype = ctypes.c_bool
        self.plaidml_add_composer_output.errcheck = self._check_err

        # PLAIDML_API bool plaidml_add_composer_dependency(plaidml_composer* composer, plaidml_applier* must_run_before);
        self.plaidml_add_composer_dependency = lib.plaidml_add_composer_dependency
        self.plaidml_add_composer_dependency.argtypes = [
            ctypes.POINTER(_C_Composer),  # plaidml_composer* composer
            ctypes.POINTER(_C_Applier)  # plaidml_applier* must_run_before
        ]
        self.plaidml_add_composer_dependency.restype = ctypes.c_bool
        self.plaidml_add_composer_dependency.errcheck = self._check_err

        # PLAIDML_API bool plaidml_add_composer_update(
        #   plaidml_composer* composer,
        #   plaidml_var* dest_tensor,
        #   plaidml_var* src_tensor
        # );
        self.plaidml_add_composer_update = lib.plaidml_add_composer_update
        self.plaidml_add_composer_update.argtypes = [
            ctypes.POINTER(_C_Composer),  # plaidml_composer* composer
            ctypes.POINTER(_C_Var),  # plaidml_var* dest_tensor
            ctypes.POINTER(_C_Var)  # plaidml_var* src_tensor
        ]
        self.plaidml_add_composer_update.restype = ctypes.c_bool
        self.plaidml_add_composer_update.errcheck = self._check_err

        # PLAIDML_API plaidml_function* plaidml_build_composed_function(plaidml_composer* composer);
        self.plaidml_build_composed_function = lib.plaidml_build_composed_function
        self.plaidml_build_composed_function.argtypes = [
            ctypes.POINTER(_C_Composer)  # plaidml_composer* composer
        ]
        self.plaidml_build_composed_function.restype = ctypes.POINTER(_C_Function)
        self.plaidml_build_composed_function.errcheck = self._check_err

        # PLAIDML_API void plaidml_free_composer(plaidml_composer* composer);
        self.plaidml_free_composer = lib.plaidml_free_composer
        self.plaidml_free_composer.argtypes = [
            ctypes.POINTER(_C_Composer)  # plaidml_composer* composer
        ]

        # PLAIDML_API plaidml_applier* plaidml_alloc_applier(plaidml_function* function);
        self.plaidml_alloc_applier = lib.plaidml_alloc_applier
        self.plaidml_alloc_applier.argtypes = [
            ctypes.POINTER(_C_Function)  # plaidml_function* function
        ]
        self.plaidml_alloc_applier.restype = ctypes.POINTER(_C_Applier)
        self.plaidml_alloc_applier.errcheck = self._check_err

        # PLAIDML_API bool plaidml_apply_add_dependency(plaidml_applier* applier, plaidml_applier* must_run_before);
        self.plaidml_apply_add_dependency = lib.plaidml_apply_add_dependency
        self.plaidml_apply_add_dependency.argtypes = [
            ctypes.POINTER(_C_Applier),  # plaidml_applier* applier
            ctypes.POINTER(_C_Applier)  # plaidml_applier* must_run_before
        ]
        self.plaidml_apply_add_dependency.restype = ctypes.c_bool
        self.plaidml_apply_add_dependency.errcheck = self._check_err

        # PLAIDML_API bool plaidml_apply_add_input(plaidml_applier* applier, const char* name, plaidml_var* var);
        self.plaidml_apply_add_input = lib.plaidml_apply_add_input
        self.plaidml_apply_add_input.argtypes = [
            ctypes.POINTER(_C_Applier),  # plaidml_applier* applier
            ctypes.c_char_p,  # const char* name
            ctypes.POINTER(_C_Var)  # plaidml_var* var
        ]
        self.plaidml_apply_add_input.restype = ctypes.c_bool
        self.plaidml_apply_add_input.errcheck = self._check_err

        # PLAIDML_API plaidml_var* plaidml_apply_alloc_output(plaidml_applier* applier, const char* name);
        self.plaidml_apply_alloc_output = lib.plaidml_apply_alloc_output
        self.plaidml_apply_alloc_output.argtypes = [
            ctypes.POINTER(_C_Applier),  # plaidml_applier* applier
            ctypes.c_char_p  # const char* name
        ]
        self.plaidml_apply_alloc_output.restype = ctypes.POINTER(_C_Var)
        self.plaidml_apply_alloc_output.errcheck = self._check_err

        # PLAIDML_API void plaidml_free_applier(plaidml_applier* applier);
        self.plaidml_free_applier = lib.plaidml_free_applier
        self.plaidml_free_applier.argtypes = [
            ctypes.POINTER(_C_Applier)  # plaidml_applier* applier
        ]

        # PLAIDML_API plaidml_invoker* plaidml_alloc_invoker(vai_ctx* ctx, plaidml_function* function);
        self.plaidml_alloc_invoker = lib.plaidml_alloc_invoker
        self.plaidml_alloc_invoker.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_Function)  # plaidml_function* function
        ]
        self.plaidml_alloc_invoker.restype = ctypes.POINTER(_C_Invoker)
        self.plaidml_alloc_invoker.errcheck = self._check_err

        # PLAIDML_API void plaidml_free_invoker(plaidml_invoker* invoker);
        self.plaidml_free_invoker = lib.plaidml_free_invoker
        self.plaidml_free_invoker.argtypes = [
            ctypes.POINTER(_C_Invoker)  # plaidml_invoker* invoker
        ]

        # PLAIDML_API bool plaidml_set_invoker_input(plaidml_invoker* invoker, const char* name, plaidml_var* var);
        self.plaidml_set_invoker_input = lib.plaidml_set_invoker_input
        self.plaidml_set_invoker_input.argtypes = [
            ctypes.POINTER(_C_Invoker),  # plaidml_invoker* invoker
            ctypes.c_char_p,  # const char* name
            ctypes.POINTER(_C_Var)  # plaidml_var* var
        ]
        self.plaidml_set_invoker_input.restype = ctypes.c_bool
        self.plaidml_set_invoker_input.errcheck = self._check_err

        # PLAIDML_API plaidml_shape* plaidml_alloc_invoker_output_shape(plaidml_invoker* invoker, const char* name);
        self.plaidml_alloc_invoker_output_shape = lib.plaidml_alloc_invoker_output_shape
        self.plaidml_alloc_invoker_output_shape.argtypes = [
            ctypes.POINTER(_C_Invoker),  # plaidml_invoker* invoker
            ctypes.c_char_p  # const char* name
        ]
        self.plaidml_alloc_invoker_output_shape.restype = ctypes.POINTER(_C_Shape)
        self.plaidml_alloc_invoker_output_shape.errcheck = self._check_err

        # PLAIDML_API bool plaidml_set_invoker_output(plaidml_invoker* invoker, const char* name, plaidml_var* var);
        self.plaidml_set_invoker_output = lib.plaidml_set_invoker_output
        self.plaidml_set_invoker_output.argtypes = [
            ctypes.POINTER(_C_Invoker),  # plaidml_invoker* invoker
            ctypes.c_char_p,  # const char* name
            ctypes.POINTER(_C_Var)  # plaidml_var* var
        ]
        self.plaidml_set_invoker_output.restype = ctypes.c_bool
        self.plaidml_set_invoker_output.errcheck = self._check_err

        # PLAIDML_API plaidml_invocation* plaidml_schedule_invocation(vai_ctx* ctx, plaidml_invoker* invoker);
        self.plaidml_schedule_invocation = lib.plaidml_schedule_invocation
        self.plaidml_schedule_invocation.argtypes = [
            ctypes.POINTER(plaidml.library._C_Context),  # vai_ctx* ctx
            ctypes.POINTER(_C_Invoker)  # plaidml_invoker* invoker
        ]
        self.plaidml_schedule_invocation.restype = ctypes.POINTER(_C_Invocation)
        self.plaidml_schedule_invocation.errcheck = self._check_err

        # PLAIDML_API void plaidml_free_invocation(plaidml_invocation* invocation);
        self.plaidml_free_invocation = lib.plaidml_free_invocation
        self.plaidml_free_invocation.argtypes = [
            ctypes.POINTER(_C_Invocation)  # plaidml_invocation* invocation
        ]

        # PLAIDML_API plaidml_gradient* plaidml_alloc_gradient(plaidml_var* var);
        self.plaidml_alloc_gradient = lib.plaidml_alloc_gradient
        self.plaidml_alloc_gradient.argtypes = [
            ctypes.POINTER(_C_Var)  # plaidml_var* var
        ]
        self.plaidml_alloc_gradient.restype = ctypes.POINTER(_C_Gradient)
        self.plaidml_alloc_gradient.errcheck = self._check_err

        # PLAIDML_API void plaidml_free_gradient(plaidml_gradient* grad);
        self.plaidml_free_gradient = lib.plaidml_free_gradient
        self.plaidml_free_gradient.argtypes = [
            ctypes.POINTER(_C_Gradient)  # plaidml_gradient* grad
        ]

        # PLAIDML_API plaidml_var* plaidml_compute_grad_wrt(plaidml_gradient* grad, plaidml_var* wrt);
        self.plaidml_compute_grad_wrt = lib.plaidml_compute_grad_wrt
        self.plaidml_compute_grad_wrt.argtypes = [
            ctypes.POINTER(_C_Gradient),  # plaidml_gradient* grad
            ctypes.POINTER(_C_Var)  # plaidml_var* wrt
        ]
        self.plaidml_compute_grad_wrt.restype = ctypes.POINTER(_C_Var)
        self.plaidml_compute_grad_wrt.errcheck = self._check_err

    def _check_err(self, result, func, args):
        if result:
            return result
        if func == self.plaidml_alloc_device_enumerator and args[2]:
            return None
        if func == self.plaidml_map_buffer_current and args[2]:
            return None
        if func == self.plaidml_writeback_mapping and args[2]:
            return None
        self.raise_last_status()


_impl_lib_lock = threading.Lock()
_impl_lib = None


def _lib():
    global _impl_lib, _impl_lib_lock

    with _impl_lib_lock:
        if not _impl_lib:
            _impl_lib = _Library()
        return _impl_lib


# Enums
_DEVICE_NAME = 1
_DEVICE_DESCRIPTION = 2
_CONFIG_ID = 3

_PROVIDER_DEVICES = 1

DATA_INVALID = 0
DATA_BOOLEAN = 2
DATA_INT8 = 0x10
DATA_INT16 = 0x11
DATA_INT32 = 0x12
DATA_INT64 = 0x13
DATA_UINT8 = 0x20
DATA_UINT16 = 0x21
DATA_UINT32 = 0x22
DATA_UINT64 = 0x23
DATA_FLOAT16 = 0x31
DATA_FLOAT32 = 0x32
DATA_FLOAT64 = 0x33

_CTYPES = {
    DATA_BOOLEAN: ctypes.c_bool,
    DATA_INT8: ctypes.c_int8,
    DATA_INT16: ctypes.c_int16,
    DATA_INT32: ctypes.c_int32,
    DATA_INT64: ctypes.c_int64,
    DATA_UINT8: ctypes.c_uint8,
    DATA_UINT16: ctypes.c_uint16,
    DATA_UINT32: ctypes.c_uint32,
    DATA_UINT64: ctypes.c_uint64,
    DATA_FLOAT16: ctypes.c_uint16,  # TODO: Implement half-width float wrapper
    DATA_FLOAT32: ctypes.c_float,
    DATA_FLOAT64: ctypes.c_double
}


def _internal_set_vlog(l):
    _lib()._internal_set_vlog(l)
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    plaidml.DEFAULT_LOG_HANDLER.setLevel(logging.NOTSET)


def get_perf_counter(name):
    return _lib().get_perf_counter(name)


def set_perf_counter(name, value):
    return _lib().set_perf_counter(name, value)


_backtraces = None


def set_backtrace(enable):
    global _backtraces
    if enable:
        _backtraces = {}
    else:
        _backtraces = None


def Context():
    return plaidml.context.Context(_lib())


class _Function(object):

    def __init__(self, f):
        self._as_parameter_ = f
        self._free = _lib().plaidml_free_function

    def __del__(self):
        if hasattr(self, '_free'):
            self._free(self)


class Function(_Function):

    def __init__(self, code, backtrace=None):
        global _backtraces
        fid = ""
        if _backtraces is not None:
            if backtrace == None:
                backtrace = "".join(traceback.format_stack()[:-1])
            fid = "id_" + hashlib.md5(backtrace + code).hexdigest()[0:12]
            if fid not in _backtraces:
                _backtraces[fid] = backtrace 
                logging.getLogger(__name__).info("Adding function ID: " + fid)
                logging.getLogger(__name__).info(code)
                logging.getLogger(__name__).info(backtrace)

        super(Function, self).__init__(_lib().plaidml_build_coded_function(code, fid))


class _DeviceConfig(object):

    def __init__(self, ctx, enumerator, config):
        self._as_parameter_ = config
        self._ctx = ctx

        # Keep the enumerator alive, since the underlying C devconf object
        # is only valid as long as the enumerator it came from.
        self._enumerator = enumerator

    @property
    def name(self):
        return self._query_str(_DEVICE_NAME)

    @property
    def config_id(self):
        return self._query_str(_CONFIG_ID)

    @property
    def description(self):
        return self._query_str(_DEVICE_DESCRIPTION)

    def _query_str(self, propid):
        blen = ctypes.c_size_t(0)
        _lib().plaidml_query_devconf(self._ctx, self, propid, None, 0, ctypes.byref(blen))
        if not blen:
            return ''
        buf = ctypes.create_string_buffer(blen.value)
        _lib().plaidml_query_devconf(self._ctx, self, propid, buf, blen, None)
        return buf.value

    def __str__(self):
        return self.name


class Device(object):

    def __init__(self, ctx, device=None):
        self._bufs = set()
        if device and not isinstance(device, _DeviceConfig):
            for d in devices(ctx, device):
                device = d
                break
        self._as_parameter_ = _lib().plaidml_open_device(ctx, device if device else None)
        self._free_buffer = _lib().plaidml_free_buffer
        self._close = _lib().plaidml_close_device
        self._ctx = ctx

    def _register_buffer(self, buf):
        plaidml_buffer = buf._as_parameter_

        def free_plaidml_buffer(wr):
            self._free_buffer(plaidml_buffer)
            self._bufs.remove(wr)

        wr = weakref.ref(buf, free_plaidml_buffer)
        self._bufs.add(wr)

    def close(self):
        if hasattr(self, '_bufs') and hasattr(self, '_free_buffer'):
            bufs = set(self._bufs)
            for wbuf in bufs:
                buf = wbuf()
                if buf and buf._as_parameter_:
                    self._free_buffer(buf)
                    buf._as_parameter_ = None
                self._bufs.remove(wbuf)

        if hasattr(self, '_close') and hasattr(self, '_as_parameter'):
            self._close(self)

        self._as_parameter_ = None

    def __del__(self):
        self.close()

    def get_context(self):
        return self._ctx


@contextlib.contextmanager
def open_device(ctx, config=None):
    dev = Device(ctx, config)
    yield dev
    dev.close()


# TODO(T1104): make this just return lists
class _Enumerator(object):

    def __init__(self, ctx, config=None):
        self._ctx = ctx
        if config:
            self._as_parameter_ = _lib().plaidml_alloc_device_enumerator_with_config(
                ctx, config, ctypes.cast(None, _ENUM_DEVICES_FUNCTYPE), None)
        else:
            self._as_parameter_ = _lib().plaidml_alloc_device_enumerator(
                ctx, ctypes.cast(None, _ENUM_DEVICES_FUNCTYPE), None)
        self._free = _lib().plaidml_free_device_enumerator

    def __del__(self):
        if hasattr(self, '_free'):
            self._free(self)

    def __getitem__(self, key):
        try:
            return _DeviceConfig(self._ctx, self, _lib().plaidml_get_devconf(self._ctx, self, key))
        except plaidml.exceptions.OutOfRange:
            raise IndexError


def devices(ctx, config=None):
    enumerator = _Enumerator(ctx, config)
    for conf in enumerator:
        yield conf


class _Buffer(object):

    def __init__(self, ctx, dev, shape):
        self._as_parameter_ = _lib().plaidml_alloc_buffer(
            ctx, dev, _lib().plaidml_get_shape_buffer_size(shape))
        self._ctx = ctx
        dev._register_buffer(self)


class _Var(object):

    def __init__(self, v):
        self._as_parameter_ = v
        self._free = _lib().plaidml_free_var

    def __del__(self):
        if hasattr(self, '_free'):
            self._free(self)


class _View(object):

    def __init__(self, ctx, mapping, dtype, ctype, length, shape, buf):
        self._as_parameter_ = mapping
        self._dtype = dtype
        self._ctype = ctype
        self._base = ctypes.cast(_lib().plaidml_get_mapping_base(ctx, self), ctypes.POINTER(ctype))
        self.contents = self._base.contents
        self._ctx = ctx
        if self._base:
            self._length = length
        else:
            self._length = 0
        self._shape = shape
        self._buf = buf

    def __del__(self):
        if self._buf:
            # This view has a reference to its source buffer; it was created as a long-term mapping.
            _lib().plaidml_free_mapping(self)
            self._buf = None

    def writeback(self):
        _lib().plaidml_writeback_mapping(self._ctx, self)

    def raw(self):
        return self._base

    def __get_dim_idx(self, key):
        dims = self._shape.dimensions
        idx = 0
        for ki in iter(key):
            dim = dims.pop(0)
            if ki < 0 or dim.size <= ki:
                raise IndexError('out of range PlaidML buffer access')
            idx += ki * dim.stride
        return idx

    def __getitem__(self, key):
        if isinstance(key, slice):
            return [self._base[idx] for idx in xrange(*key.indices(self._length))]

        try:
            idx = self.__get_dim_idx(key)
        except TypeError:
            idx = key

        if idx < 0:
            idx = self._length + idx

        if idx < 0 or self._length <= idx:
            raise IndexError('out of range PlaidML buffer access')

        return self._base[idx]

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            e = enumerate(value)
            for idx in xrange(*key.indices(self._length)):
                _, v = e.next()
                self._base[idx] = v
            return

        try:
            idx = self.__get_dim_idx(key)
        except TypeError:
            idx = key

        if idx < 0:
            idx = self._length + idx

        if idx < 0 or self._length <= idx:
            raise IndexError('out of range PlaidML buffer access')

        # Special handling since float16 is a placed into a uint16 on the C side
        # (since C has no half type), and yet we want the move the actual bits
        # across (not cast float -> int)
        if self._dtype == DATA_FLOAT16:
            # Do a reinterpet cast... Is there a better way to do this?
            varray = np.array([0], dtype='float16')
            varray[0] = value
            value = varray.view(dtype='uint16')[0]

        self._base[idx] = value

    def as_ndarray(self):
        ar = np.ctypeslib.as_array(self, shape=tuple(dim.size for dim in self._shape.dimensions))
        if self._dtype == DATA_FLOAT16:
            ar = src.view(dtype='float16')
        return ar

    def copy_from_ndarray(self, src):
        if self._dtype == DATA_FLOAT16:
            if src.dtype != 'float16':
                src = src.astype('float16')
            src = src.view(dtype='uint16')
        dst = np.ctypeslib.as_array(self, shape=src.shape)
        np.copyto(dst, src)

    def copy_to_ndarray(self, dst):
        src = np.ctypeslib.as_array(self, shape=dst.shape)
        if self._dtype == DATA_FLOAT16:
            src = src.view(dtype='float16')
        np.copyto(dst, src)

    def __len__(self):
        return self._length

    def __iter__(self):
        for idx in xrange(self._length):
            yield self[idx]


class Tensor(_Var):

    def __init__(self, dev, shape, copy_buffer=False):
        self._shape = shape
        if copy_buffer:
            self._buffer = copy_buffer
        else:
            self._buffer = _Buffer(dev.get_context(), dev, shape)
        super(Tensor,
              self).__init__(_lib().plaidml_alloc_tensor(dev.get_context(), self.buffer, shape))

    @property
    def buffer(self):
        return self._buffer

    @property
    def shape(self):
        return self._shape

    @contextlib.contextmanager
    def mmap_current(self):
        mapping = _lib().plaidml_map_buffer_current(self.buffer,
                                                    ctypes.cast(None, _MAP_BUFFER_FUNCTYPE), None)
        yield _View(self.buffer._ctx, mapping, self.shape.dtype, self.shape.ctype,
                    _lib().plaidml_get_shape_element_count(self.shape), self.shape, None)
        _lib().plaidml_free_mapping(mapping)

    @contextlib.contextmanager
    def mmap_discard(self, ctx):
        mapping = _lib().plaidml_map_buffer_discard(ctx, self.buffer)
        yield _View(ctx, mapping, self.shape.dtype, self.shape.ctype,
                    _lib().plaidml_get_shape_element_count(self.shape), self.shape, None)
        _lib().plaidml_free_mapping(mapping)

    def as_ndarray(self, ctx):
        mapping = _lib().plaidml_map_buffer_current(self.buffer,
                                                    ctypes.cast(None, _MAP_BUFFER_FUNCTYPE), None)
        return _View(ctx, mapping, self.shape.dtype, self.shape.ctype,
                     _lib().plaidml_get_shape_element_count(self.shape), self.shape,
                     self).as_ndarray()


class Integer(_Var):

    def __init__(self, value):
        super(Integer, self).__init__(_lib().plaidml_alloc_int64(value))


class Real(_Var):

    def __init__(self, value):
        super(Real, self).__init__(_lib().plaidml_alloc_real(value))


Dimension = namedtuple('Dimension', ['size', 'stride'])


class _Shape(object):

    def __init__(self, ctx, shape):
        self._as_parameter_ = shape
        self._free = _lib().plaidml_free_shape
        self._dtype = _lib().plaidml_get_shape_type(self)
        self._ctype = _CTYPES[self._dtype]
        self._ctx = ctx

    def __del__(self):
        if hasattr(self, '_free'):
            self._free(self)

    @property
    def ctype(self):
        return self._ctype

    @property
    def dtype(self):
        return self._dtype

    @property
    def offset(self, off):
        return _lib().plaidml_get_shape_offset(self)

    @offset.setter
    def set_offset(self, off):
        _lib().plaidml_set_shape_offset(self._ctx, self, off)

    @property
    def dimension_count(self):
        return _lib().plaidml_get_shape_dimension_count(self)

    @property
    def dimensions(self):
        return [
            Dimension(_lib().plaidml_get_shape_dimension_size(self, dix),
                      _lib().plaidml_get_shape_dimension_stride(self, dix))
            for dix in xrange(self.dimension_count)
        ]


class Shape(_Shape):

    def __init__(self, ctx, dtype, *args):
        super(Shape, self).__init__(ctx, _lib().plaidml_alloc_shape(ctx, dtype))
        stride = 1
        for arg in args:
            stride *= arg
        for arg in args:
            stride /= arg
            _lib().plaidml_add_dimension(ctx, self, arg, stride)


class Placeholder(_Var):

    def __init__(self, dims):
        super(Placeholder, self).__init__(_lib().plaidml_alloc_placeholder(dims))


def _as_plaidml_var(value):
    if isinstance(value, _Var):
        return value
    if isinstance(value, long):
        return _Var(_lib().plaidml_alloc_int64(value))
    if isinstance(value, int):
        return _Var(_lib().plaidml_alloc_int64(value))
    if isinstance(value, float) or value.dtype.name == 'float32':
        return _Var(_lib().plaidml_alloc_real(value))
    if value.shape == ():  # This should mean we have a 0-D numpy array
        if value.dtype.name == 'int_':
            return _Var(_lib().plaidml_alloc_int64(value))
        if value.dtype.name == 'float_' or value.dtype.name == 'float32':
            return _Var(_lib().plaidml_alloc_real(value))
        else:
            raise plaidml.exceptions.InvalidArguments('Unexpected type in array: ' +
                                                      value.dtype.name)
    else:
        raise plaidml.exceptions.InvalidArguments(
            'unable to convert high dim array to PlaidML value: shape = ' + str(value.shape))
    raise plaidml.exceptions.InvalidArguments(
        'unable to convert \'%s\' to a PlaidML value' % value)


class Applier(object):

    def __init__(self, ctx, f):
        self._as_parameter_ = _lib().plaidml_alloc_applier(f)
        self._free = _lib().plaidml_free_applier
        self._ctx = ctx

    def __del__(self):
        if hasattr(self, '_free'):
            self._free(self)

    def add_input(self, name, value):
        _lib().plaidml_apply_add_input(self, name, _as_plaidml_var(value))

    def get_output_shape(self, name):
        return _Shape(self._ctx, _lib().plaidml_apply_alloc_output_shape(self, name))

    def add_output(self, name):
        return _Var(_lib().plaidml_apply_alloc_output(self, name))


class Composer(object):

    def __init__(self):
        self._as_parameter_ = _lib().plaidml_alloc_composer()
        self._free = _lib().plaidml_free_composer

    def __del__(self):
        if hasattr(self, '_free'):
            self._free(self)

    def add_input(self, name, val):
        _lib().plaidml_add_composer_input(self, name, val)

    def add_output(self, name, val):
        _lib().plaidml_add_composer_output(self, name, val)

    def add_dependency(self, applier):
        _lib().plaidml_add_composer_dependency(self, applier)

    def add_update(self, dest, src):
        _lib().plaidml_add_composer_update(self, dest, src)

    def build(self):
        return _Function(_lib().plaidml_build_composed_function(self))


class Invoker(object):

    def __init__(self, ctx, f, inputs={}, outputs={}):
        self._as_parameter_ = _lib().plaidml_alloc_invoker(ctx, f)
        self._free = _lib().plaidml_free_invoker
        self._ctx = ctx
        self.set_inputs(inputs)
        self.set_outputs(outputs)

    def __del__(self):
        if hasattr(self, '_free'):
            self._free(self)

    def set_input(self, name, value):
        _lib().plaidml_set_invoker_input(self, name, _as_plaidml_var(value))

    def set_inputs(self, inputs):
        for (name, value) in inputs.iteritems():
            self.set_input(name, value)

    def get_output_shape(self, name):
        return _Shape(self._ctx, _lib().plaidml_alloc_invoker_output_shape(self, name))

    def set_output(self, name, value):
        _lib().plaidml_set_invoker_output(self, name, _as_plaidml_var(value))

    def set_outputs(self, outputs):
        for (name, value) in outputs.iteritems():
            self.set_output(name, value)

    def invoke(self):
        return Invocation(self._ctx, self)


class Invocation(object):

    def __init__(self, ctx, invoker):
        self._as_parameter_ = _lib().plaidml_schedule_invocation(ctx, invoker)
        self._free = _lib().plaidml_free_invocation

    def __del__(self):
        if hasattr(self, '_free'):
            self._free(self)


def gradients(loss, variables):
    g = _lib().plaidml_alloc_gradient(loss)
    try:
        return [_Var(_lib().plaidml_compute_grad_wrt(g, var)) for var in variables]
    finally:
        _lib().plaidml_free_gradient(g)


def run(ctx, f, inputs={}, outputs={}):
    Invoker(ctx, f, inputs, outputs).invoke()
