# -*- coding: utf-8 -*-
"""
Created on Mon Jun  3 14:16:29 2024

@author: mohacsi_i
"""

from time import sleep
from ophyd import Device, Signal, SignalRO, Component
from std_daq_client import StdDaqClient









class StdDaqClientDevice(Device):
    """ Lightweight wrapper around the official StdDaqClient ophyd package.
        Coincidentally also the StdDaqClient is using a Redis broker, that can 
        potentially be directly fed to the BEC.
    
    """
    # Status attributes
    num_images = Component(SignalRO)
    num_images_counter = Component(SignalRO)
    output_file = Component(SignalRO)
    run_id = Component(SignalRO)
    state = Component(SignalRO)
    
    # Configuration attributes
    bit_depth = Component(SignalRO)
    detector_name = Component(SignalRO)
    detector_type = Component(SignalRO)
    image_pixel_width = Component(SignalRO)
    image_pixel_height = Component(SignalRO)
    start_udp_port = Component(SignalRO)
    
    def __init__(self, *args, parent: Device = None, **kwargs) -> None:
        super().__init__(*args, parent=parent, **kwargs)
        self.std_rest_server_url = (
            kwargs["rest_server_url"] if "file_writer_url" in kwargs else "http://localhost:5000"
        )
        self.client = StdDaqClient(url_base=self.std_rest_server_url)
        self._n_images = None
        self._output_file = None
        # Fill signals from current DAQ config
        self.poll_device_config()
        self.poll()
        
    
    
    def configure(self, d: dict) -> tuple:
        """
        Example:
            std.configure(d={'bit_depth': 16, 'writer_user_id': 0})
        
        """
        if "n_images" in d:
            self._n_images = d['n_images']
            del d['n_images']
        if "output_file" in d:
            self._output_file = d['output_file']
            del d['output_file']        
        
        old_config = self.client.get_config()
        
        self.client.set_config(daq_config=d)
    
        new_config = self.client.get_config()
        return (old_config, new_config)


    def stage(self):
        self.client.start_writer_async({'output_file': self._output_file, 'n_images': self._n_images})
        
        return
        #while True:
        #    sleep(0.1)
        #    daq_status = self.client.get_status()
        #    if daq_status['acquisition']['state'] in ["ACQUIRING"]:
        #        break
        
    def unstage(self):
        self.client.stop_writer()

    def stop(self):
        self.client.stop_writer()

    def poll(self):
        
        daq_status = self.client.get_status()
        
        # Put if new value (put runs subscriptions) 
        if self.n_images.value != daq_status['acquisition']['info']['n_images']:
            self.n_images.put(daq_status['acquisition']['info']['n_images'])
        
        if self.n_written.value != daq_status['acquisition']['stats']['n_write_completed']:
            self.n_written.put(daq_status['acquisition']['stats']['n_write_completed'])

        if self.output_file.value != daq_status['acquisition']['info']['output_file']:
            self.output_file.put(daq_status['acquisition']['info']['output_file'])
            
        if self.run_id.value != daq_status['acquisition']['info']['run_id']:
            self.run_id.put(daq_status['acquisition']['info']['run_id'])
        
        if self.state.value != daq_status['acquisition']['state']:
            self.state.put(daq_status['acquisition']['state'])

        
    def poll_device_config(self):
        
        daq_config = self.client.get_config()
        
        # Put if new value (put runs subscriptions) 
        if self.bit_depth.value != daq_config['bit_depth']:
            self.bit_depth.put(daq_config['bit_depth'])
        
        if self.detector_name.value != daq_config['detector_name']:
            self.detector_name.put(daq_config['detector_name'])

        if self.detector_type.value != daq_config['detector_type']:
            self.detector_type.put(daq_config['detector_type'])
            
        if self.image_pixel_width.value != daq_config['image_pixel_width']:
            self.image_pixel_width.put(daq_config['image_pixel_width'])              
            
        if self.image_pixel_height.value != daq_config['image_pixel_height']:
            self.image_pixel_height.put(daq_config['image_pixel_height'])
            
        if self.start_udp_port.value != daq_config['start_udp_port']:
            self.start_udp_port.put(daq_config['start_udp_port'])        
            
            
            
            
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        

