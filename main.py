"""People Counter."""
"""
 Copyright (c) 2018 Intel Corporation.
 Permission is hereby granted, free of charge, to any person obtaining
 a copy of this software and associated documentation files (the
 "Software"), to deal in the Software without restriction, including
 without limitation the rights to use, copy, modify, merge, publish,
 distribute, sublicense, and/or sell copies of the Software, and to
 permit person to whom the Software is furnished to do so, subject to
 the following conditions:
 The above copyright notice and this permission notice shall be
 included in all copies or substantial portions of the Software.
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
 LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
 OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
 WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""


import os
import sys
import time
import socket
import json
import cv2

import logging as log
import paho.mqtt.client as mqtt

from argparse import ArgumentParser
from inference import Network

# MQTT server environment variables
HOSTNAME = socket.gethostname()
IPADDRESS = socket.gethostbyname(HOSTNAME)
MQTT_HOST = IPADDRESS
MQTT_PORT = 3001
MQTT_KEEPALIVE_INTERVAL = 60


def build_argparser():
    """
    Parse command line arguments.

    :return: command line arguments
    """
    parser = ArgumentParser()
    parser.add_argument("-m", "--model", required=True, type=str,
                        help="Path to an xml file with a trained model.")
    parser.add_argument("-i", "--input", required=True, type=str,
                        help="Path to image or video file")
    parser.add_argument("-l", "--cpu_extension", required=False, type=str,
                        default=None,
                        help="MKLDNN (CPU)-targeted custom layers."
                             "Absolute path to a shared library with the"
                             "kernels impl.")
    parser.add_argument("-d", "--device", type=str, default="CPU",
                        help="Specify the target device to infer on: "
                             "CPU, GPU, FPGA or MYRIAD is acceptable. Sample "
                             "will look for a suitable plugin for device "
                             "specified (CPU by default)")
    parser.add_argument("-pt", "--prob_threshold", type=float, default=0.5,
                        help="Probability threshold for detections filtering"
                        "(0.5 by default)")
    return parser


def connect_mqtt():
    ### TODO: Connect to the MQTT client ###
    client = mqtt.Client()
    client. connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE_INTERVAL)

    return client
### Pre-process the image

def preprocess_image(frame, input_shape):
    """
        Pre-process image as needed
        :param frame: from cv2.VideoCapture().read()
        :param input_shape
        :return preprocessed image
    """
    image = cv2.resize(frame, (input_shape[3], input_shape[2]))
    image_p = image.transpose((2,0,1))
    image_p = image_p.reshape(1, *image_p.shape)
    return image_p

def draw(probs, frame, net_output, pointer, prob_threshold, w, h):
    for i, p in enumerate(probs):
        if p > prob_threshold:
            pointer += 1
            box = net_output[0, 0, i, 3:]
            p1 = (int(box[0] * w), int(box[1] * h))
            p2 = (int(box[2] * w), int(box[3] * h))
            frame = cv2.rectangle(frame, p1, p2, (0, 255, 0), 3)
            
    return frame, pointer

def infer_on_stream(args, client):
    """
    Initialize the inference network, stream video to network,
    and output stats and video.

    :param args: Command line arguments parsed by `build_argparser()`
    :param client: MQTT client
    :return: None
    """
    # Initialise the class
    infer_network = Network()
    # Set Probability threshold for detections
    prob_threshold = args.prob_threshold

    ### TODO: Load the model through `infer_network` ###
    infer_network.load_model(args.model, args.cpu_extension,args.device)
    infer_network_input_shape = infer_network.get_input_shape()
    ### TODO: Handle the input stream ###
    single_image_mode = False
    if args.input == 'CAM':
        input_validated = 0

    # Checks for input image
    elif args.input.endswith('.jpg') or args.input.endswith('.bmp') :
        single_image_mode = True
        input_validated = args.input

    # Checks for video file
    elif args.input.endswith('.mp4') or args.input.endswith('.avi'):
        input_validated = args.input
        assert os.path.isfile(args.input), "file doesn't exist"
    # Logs error if file does not satisfy the above conditions
    else :
        log.error("File is not correct")
        return
    capture = cv2.VideoCapture(args.input)
    capture.open(args.input)
    
    w = int(capture.get(3))
    h = int(capture.get(4))
    
    input_shape = infer_network_input_shape['image_tensor']
    '''
    request_id = 0
    current_count = 0
    count = 0
    duration = 0
    total_count = 0
    '''
    #iniatilize variables
    
    duration_prev = 0
    counter_total = 0
    dur = 0
    request_id=0
    
    report = 0
    counter = 0
    counter_prev = 0
    
    ### TODO: Loop until stream is over ###
    while capture.isOpened():
        
        ### TODO: Read from the video capture ###
        flag, frame = capture.read()
        ### TODO: Pre-process the image as needed ###
        if not flag:
            break
            
        image_p = preprocess_image(frame, input_shape)
        
        
        ### TODO: Start asynchronous inference for specified request ###
        net_input = {'image_tensor': image_p,'image_info': image_p.shape[1:]}
        duration_report = None
        infer_network.exec_net(net_input, request_id)
       
        ### TODO: Wait for the result ###
        if infer_network.wait() == 0:
            
            ### TODO: Get the results of the inference request ###
            net_output = infer_network.get_output()
           
           
            ### TODO: Extract any desired stats from the results ###
            pointer = 0
            probs = net_output[0, 0, :, 2]
            
            frame, pointer  = draw(probs,frame, net_output, pointer, prob_threshold, w, h) 
            if pointer == counter:
                dur += 1
                if dur >= 3:
                    report = counter
                    if dur == 3 and counter > counter_prev:
                        counter_total += counter - counter_prev
                    elif dur == 3 and counter < counter_prev:
                        duration_report = int(duration_prev)
            else:
                counter_prev = counter
                counter = pointer
                if dur >= 3:
                    duration_prev = dur
                    dur = 0
                else:
                    dur = duration_prev + dur
                    duration_prev = 0  
                    
            ### TODO: Calculate and send relevant information on ###
            ### current_count, total_count and duration to the MQTT server ###
            ### Topic "person": keys of "count" and "total" ###
            ### Topic "person/duration": key of "duration" ###
            #start_time = time.time()
            #print(start_time)
            client.publish('person',
                           payload=json.dumps({
                               'count': report, 'total': counter_total}),
                           qos=0, retain=False)
            if duration_report is not None:
                client.publish('person/duration',
                               payload=json.dumps({'duration': duration_report}),
                               qos=0, retain=False)
           
        ### TODO: Send the frame to the FFMPEG server ###
            frame = cv2.resize(frame, (768, 432))
            sys.stdout.buffer.write(frame)
            sys.stdout.flush()
        ### TODO: Write an output image if `single_image_mode` ###
            if single_image_mode:
                cv2.imwrite('output_image.jpg', frame)
                
    capture.release()
    cv2.destroyAllWindows()

def main():
    """
    Load the network and parse the output.

    :return: None
    """
    # Grab command line args
    args = build_argparser().parse_args()
    # Connect to the MQTT server
    client = connect_mqtt()
    # Perform inference on the input stream
    infer_on_stream(args, client)


if __name__ == '__main__':
    main()
