from keras import Model, Input
from keras.applications import DenseNet169
from keras.layers import UpSampling2D, Conv2D, BatchNormalization, Activation, concatenate, Add, Dense, multiply, AveragePooling2D, Lambda, MaxPooling2D, Dropout, Conv2DTranspose
from keras.utils import get_file
import keras.backend as K
from models.resnets import ResNet34

resnet_filename = 'ResNet-{}-model.keras.h5'
resnet_resource = 'https://github.com/fizyr/keras-models/releases/download/v0.0.1/{}'.format(resnet_filename)


def download_resnet_imagenet(v):
    v = int(v.replace('resnet', ''))

    filename = resnet_filename.format(v)
    resource = resnet_resource.format(v)
    if v == 50:
        checksum = '3e9f4e4f77bbe2c9bec13b53ee1c2319'
    elif v == 101:
        checksum = '05dc86924389e5b401a9ea0348a3213c'
    elif v == 152:
        checksum = '6ee11ef2b135592f8031058820bb9e71'

    return get_file(
        filename,
        resource,
        cache_subdir='models',
        md5_hash=checksum
    )


def conv_bn_relu(input, num_channel, kernel_size, stride, name, padding='same', bn_axis=-1, bn_momentum=0.99,
                 bn_scale=True, use_bias=True):
    x = Conv2D(filters=num_channel, kernel_size=(kernel_size, kernel_size),
               strides=stride, padding=padding,
               kernel_initializer="he_normal",
               use_bias=use_bias,
               name=name + "_conv")(input)
    x = BatchNormalization(name=name + '_bn', scale=bn_scale, axis=bn_axis, momentum=bn_momentum, epsilon=1.001e-5, )(x)
    x = Activation('relu', name=name + '_relu')(x)
    return x


def conv_bn(input, num_channel, kernel_size, stride, name, padding='same', bn_axis=-1, bn_momentum=0.99, bn_scale=True,
            use_bias=True):
    x = Conv2D(filters=num_channel, kernel_size=(kernel_size, kernel_size),
               strides=stride, padding=padding,
               kernel_initializer="he_normal",
               use_bias=use_bias,
               name=name + "_conv")(input)
    x = BatchNormalization(name=name + '_bn', scale=bn_scale, axis=bn_axis, momentum=bn_momentum, epsilon=1.001e-5, )(x)
    return x


def conv_relu(input, num_channel, kernel_size, stride, name, padding='same', use_bias=True, activation='relu'):
    x = Conv2D(filters=num_channel, kernel_size=(kernel_size, kernel_size),
               strides=stride, padding=padding,
               kernel_initializer="he_normal",
               use_bias=use_bias,
               name=name + "_conv")(input)
    x = Activation(activation, name=name + '_relu')(x)
    return x


def decoder_block(input, filters, skip, block_name):
    x = UpSampling2D()(input)
    x = conv_bn_relu(x, filters, 3, stride=1, padding='same', name=block_name + '_conv1')
    x = concatenate([x, skip], axis=-1, name=block_name + '_concat')
    x = conv_bn_relu(x, filters, 3, stride=1, padding='same', name=block_name + '_conv2')
    return x


def decoder_block_no_bn(input, filters, skip, block_name, activation='relu'):
    x = UpSampling2D()(input)
    x = conv_relu(x, filters, 3, stride=1, padding='same', name=block_name + '_conv1', activation=activation)
    x = concatenate([x, skip], axis=-1, name=block_name + '_concat')
    x = conv_relu(x, filters, 3, stride=1, padding='same', name=block_name + '_conv2', activation=activation)
    return x



def create_pyramid_features(C1, C2, C3, C4, C5, feature_size=256):
    P5 = Conv2D(feature_size, kernel_size=1, strides=1, padding='same', name='P5', kernel_initializer="he_normal")(C5)
    P5_upsampled = UpSampling2D(name='P5_upsampled')(P5)

    P4 = Conv2D(feature_size, kernel_size=1, strides=1, padding='same', name='C4_reduced',
                kernel_initializer="he_normal")(C4)
    P4 = Add(name='P4_merged')([P5_upsampled, P4])
    P4 = Conv2D(feature_size, kernel_size=3, strides=1, padding='same', name='P4', kernel_initializer="he_normal")(P4)
    P4_upsampled = UpSampling2D(name='P4_upsampled')(P4)

    P3 = Conv2D(feature_size, kernel_size=1, strides=1, padding='same', name='C3_reduced',
                kernel_initializer="he_normal")(C3)
    P3 = Add(name='P3_merged')([P4_upsampled, P3])
    P3 = Conv2D(feature_size, kernel_size=3, strides=1, padding='same', name='P3', kernel_initializer="he_normal")(P3)
    P3_upsampled = UpSampling2D(name='P3_upsampled')(P3)

    P2 = Conv2D(feature_size, kernel_size=1, strides=1, padding='same', name='C2_reduced',
                kernel_initializer="he_normal")(C2)
    P2 = Add(name='P2_merged')([P3_upsampled, P2])
    P2 = Conv2D(feature_size, kernel_size=3, strides=1, padding='same', name='P2', kernel_initializer="he_normal")(P2)
    P2_upsampled = UpSampling2D(size=(2, 2), name='P2_upsampled')(P2)

    P1 = Conv2D(feature_size, kernel_size=1, strides=1, padding='same', name='C1_reduced',
                kernel_initializer="he_normal")(C1)
    P1 = Add(name='P1_merged')([P2_upsampled, P1])
    P1 = Conv2D(feature_size, kernel_size=3, strides=1, padding='same', name='P1', kernel_initializer="he_normal")(P1)

    return P1, P2, P3, P4, P5

def prediction_fpn_block(x, name, upsample=None):
    x = conv_relu(x, 128, 3, stride=1, name="predcition_" + name + "_1")
    x = conv_relu(x, 128, 3, stride=1, name="prediction_" + name + "_2")
    if upsample:
        x = UpSampling2D(upsample)(x)
    return x


def resnet34_fpn(input_shape, channels=1):
    img_input = Input(input_shape)
    resnet_base = ResNet34(img_input,include_top=False)
    conv1 = resnet_base.get_layer("conv1_relu").output  # First activation
    conv2 = resnet_base.get_layer("res2b2_relu").output # Intermediate activation
    conv3 = resnet_base.get_layer("res3b3_relu").output # Intermediate activation
    conv4 = resnet_base.get_layer("res4b5_relu").output # Intermediate activation
    conv5 = resnet_base.get_layer("res5b2_relu").output  # Last activation
    P1, P2, P3, P4, P5 = create_pyramid_features(conv1, conv2, conv3, conv4, conv5)
    x = concatenate(
            [
                prediction_fpn_block(P5, "P5", (8, 8)),
                prediction_fpn_block(P4, "P4", (4, 4)),
                prediction_fpn_block(P3, "P3", (2, 2)),
                prediction_fpn_block(P2, "P2"),
            ]
        )
    x = conv_bn_relu(x, 256, 3, (1, 1), name="aggregation")
    x = decoder_block_no_bn(x, 128, conv1, 'up4')
    x = conv_relu(x, 64, 3, (1, 1), name="up5_conv1")
    x = conv_relu(x, 64, 12, (1, 1), name="up5_conv2", padding='valid')
    x = Conv2D(channels, (1, 1), activation=None)(x)
    output_layer =  Activation('sigmoid')(x)
    return Model(img_input, x)


def BatchActivate(x):
    x = BatchNormalization()(x)
    x = Activation('relu')(x)
    return x

def convolution_block(x, filters, size, strides=(1,1), padding='same', activation=True):
    x = Conv2D(filters, size, strides=strides, padding=padding)(x)
    if activation == True:
        x = BatchActivate(x)
    return x

def residual_block(blockInput, num_filters=16, batch_activate = False):
    x = BatchActivate(blockInput)
    x = convolution_block(x, num_filters, (3,3) )
    x = convolution_block(x, num_filters, (3,3), activation=False)
    x = Add()([x, blockInput])
    if batch_activate:
        x = BatchActivate(x)
    return x

def build_model(input_shape, start_channels=16, depth=4, kernel=7,  drop_out = 0.5):
    input_layer = Input(input_shape)
    conv = input_layer
    conv_layers = []
    for i in range(depth): 
        conv = Conv2D(start_channels * (2**i), (kernel, kernel), activation=None, padding="valid")(conv)
        conv = residual_block(conv,start_channels * (2**i))
        conv = residual_block(conv,start_channels * (2**i), True)
        conv_layers.append(conv)
#         conv = MaxPooling2D((2, 2))(conv)
        conv = Dropout(drop_out)(conv)

    # Middle
    convm = Conv2D(start_channels * (2**depth), (kernel, kernel), activation=None, padding="valid")(conv)
    convm = residual_block(convm,start_channels * (2**depth))
    convm = residual_block(convm,start_channels * (2**depth), True)
    uconv = convm
    
    for i in reversed(range(depth)):
        deconv = Conv2DTranspose(start_channels * (2**i), (kernel, kernel), strides=(1, 1), padding="valid")(uconv)
        uconv = concatenate([deconv, conv_layers[i]])
        uconv = Dropout(drop_out)(uconv)

        uconv = Conv2D(start_channels * (2**i), (kernel, kernel), activation=None, padding="same")(uconv)
        uconv = residual_block(uconv,start_channels * (2**i))
        uconv = residual_block(uconv,start_channels * (2**i), True)
    
    
    output_layer_noActi = Conv2DTranspose(1, (kernel,kernel), padding="valid", activation=None)(uconv)
    output_layer =  Activation('sigmoid')(output_layer_noActi)
    
    return Model(input_layer, output_layer)
