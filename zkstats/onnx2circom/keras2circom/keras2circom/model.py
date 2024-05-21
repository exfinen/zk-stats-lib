# Read keras model into list of parameters like op, input, output, weight, bias
from __future__ import annotations
from dataclasses import dataclass
import typing

import numpy as np
import keras


# <KerasTensor shape=(), dtype=float32, sparse=False, name=keras_tensor_10>
class KerasTensor(typing.Protocol):
    shape: typing.Sequence[int]
    dtype: np.dtype
    sparse: bool
    name: str


@dataclass(frozen=True)
class Input:
    is_constant: bool
    shape: typing.Sequence[int]
    # If it's a constant, name is None. Else, it's the name of the input in keras model.
    name: typing.Optional[str]
    # If it's a constant, value is the value of the constant. Else, it's None
    value: typing.Optional[float]


# read each layer in a model and convert it to a class called Layer
@dataclass
class Layer:
    ''' A single layer in a Keras model. '''
    op: str
    name: str
    inputs: list[Input]
    outputs: list[KerasTensor]
    config: dict

    def __init__(self, layer: keras.layers.Layer):
        self.op = layer.__class__.__name__
        self.name = layer.name
        # Always convert to list for easier handling. Doing this since if there is only one input, it is not a list in keras layer
        _inputs = layer.input if isinstance(layer.input, list) else [layer.input]
        # Always convert to list for easier handling. Doing this since if there is only one output, it is not a list in keras layer
        self.outputs = layer.output if isinstance(layer.output, list) else [layer.output]
        _config = layer.get_config()
        self.config = _config
        self.inputs = []
        list_inputs = _config['node_inputs']

        for index, ele_name in enumerate(list_inputs):
            # non-constant: {'class_name': '__keras_tensor__', 'config': {'shape': [1, 3, 1], 'dtype': 'float32', 'keras_history': ['input_layer', 0, 0]}, 'name': 'input_layer'},
            # constant: 3.0
            config_ele = _config['tensor_grap'][ele_name]
            # it's not a constant, add the name of the input
            is_non_constant = isinstance(config_ele, dict) and config_ele["class_name"]=='__keras_tensor__'
            # if it's constant, get the shape from non-constant input
            if is_non_constant:
                name = _inputs[index].name
                value = None
                input_shape = tuple(config_ele['config']['shape'])
                if input_shape == ():
                    # if there are more than 1 inputs like `TFAdd`, we need to get the shape of the other input
                    if len(_inputs)==2 and len(_inputs[1-index].shape)>=2:
                        input_shape = (_inputs[1-index]).shape[:-1]
                    else:
                        input_shape =(1,1)
            else:
                name = None
                value = int(config_ele)
                if len(_inputs)>0 and len(_inputs[0].shape)>=2:
                    input_shape = (_inputs[0]).shape[:-1]
                else:
                    input_shape =(1,1)
            self.inputs.append(
                Input(
                    is_constant=not is_non_constant,
                    shape=input_shape,
                    name=name,
                    value=value,
                )
            )


class Model:
    layers: typing.List[Layer]
    # The inputs to the model (the highest level inputs). E.g. input_layer
    model_inputs: typing.List[KerasTensor]
    # The outputs of the model (the highest level outputs).
    model_outputs: typing.List[KerasTensor]
    supported_ops: typing.Dict[str, keras.layers.Layer]
    skip_ops: typing.Dict[str, keras.layers.Layer]

    def __init__(self, filename: str, supported_ops: typing.List[keras.layers.Layer], skip_ops: typing.List[keras.layers.Layer]):
        ''' Load a Keras model from a file. '''
        self.supported_ops = {op.__name__: op for op in supported_ops}
        self.skip_ops = {op.__name__: op for op in skip_ops}
        # edit : allow reading customed layer
        keras.saving.get_custom_objects().clear()
        with keras.saving.custom_object_scope(self.supported_ops):
            model = keras.models.load_model(filename)
        # E.g. model.inputs=[<KerasTensor shape=(1, 2, 1), dtype=float32, sparse=False, name=input_layer>],
        self.model_inputs = model.inputs
        # E.g. model.outputs=<KerasTensor shape=(), dtype=float32, sparse=False, name=keras_tensor_10>
        self.model_outputs = model.outputs
        self.layers = [Layer(layer) for layer in model.layers if self._for_transpilation(layer.__class__.__name__)]
        # Map each output to their layer for later usage
        self.map_output_to_component: dict[str, Layer] = {}
        for layer in self.layers:
            for output in layer.outputs:
                if output.name in self.map_output_to_component:
                    raise ValueError(f"Output name {output.name} is already used by another layer.")
                self.map_output_to_component[output.name] = layer
        print('\n\n\n\n\n MPAPPPA: ', self.map_output_to_component.keys())
        print('\n\n\n\n\n\n')
    def get_component_from_output_name(self, output_name: str) -> typing.Optional[Layer]:
        try:
            return self.map_output_to_component[output_name]
        except KeyError:
            return None

    def is_model_input(self, input_name: str):
        return input_name in [inp.name for inp in self.model_inputs]

    def _for_transpilation(self, op: str) -> bool:
        if op in self.skip_ops:
            return False
        if op in self.supported_ops:
            return True
        raise NotImplementedError(f'Unsupported op: {op}')
