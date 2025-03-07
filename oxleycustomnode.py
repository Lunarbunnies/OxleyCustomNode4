import sys
import os

# Get the directory of the current script
current_script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to the external_packages directory
external_packages_path = os.path.join(current_script_dir, 'external_packages')

# Add this path to sys.path
sys.path.append(external_packages_path)

import select
import ssl 
import requests
from io import BytesIO
from PIL import Image, ImageDraw
import numpy as np
import torch  # Import torch
import websocket
from websocket import WebSocketTimeoutException
import json
from json.decoder import JSONDecodeError
import base64
from datetime import datetime, timedelta

def get_latest_message(ws):
    latest_message = None
    try:
        while True:  # Keep reading until buffer is empty
            message = ws.recv()
            latest_message = message  # ✅ Only keep the newest message
    except WebSocketTimeoutException:
        pass  # ✅ Don't treat timeout as an error, just return the latest frame
    except Exception as e:
        print(f"⚠️ WebSocket error: {e}")
        if ws:
            ws.close()
        return None
    return latest_message
    

class OxleyAlternatorNode:
    counter = 0

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"image_in": ("IMAGE", {})},
        }

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("image_out1", "image_out2")
    FUNCTION = "alternate"
    CATEGORY = "oxley"

    def alternate(self, image_in):
        output1 = None
        output2 = None
        if OxleyAlternatorNode.counter % 2 == 0:
            output1 = image_in
            output2 = None
        else:
            output1 = None
            output2 = image_in
        OxleyAlternatorNode.counter += 1
        return (output1, output2)


class OxleyWebsocketDownloadImageNode:
    placeholder_tensor = None  # Cache placeholder tensor
    ws_connections = {}  # Class-level dictionary to store WebSocket connections by unique key
    global_counter = 0  # Global counter
    
    @classmethod
    def get_connection(cls, ws_url, node_id):
        """Get an existing WebSocket connection or create a new one, checking for validity."""
        connection_key = f"{ws_url}_{node_id}"
        existing_connection = cls.ws_connections.get(connection_key)
    
        if existing_connection:
            try:
                existing_connection.settimeout(0.1)  # ✅ Validate WebSocket by attempting a receive
                existing_connection.recv()
                existing_connection.settimeout(None)  # Reset timeout after validation
                return existing_connection
            except websocket.WebSocketException:
                print(f"⚠️ WebSocket error, reconnecting: {ws_url}")
                existing_connection.close()
                del cls.ws_connections[connection_key]
    
        try:
            print(f"🔄 Creating new WebSocket connection to {ws_url}")
            new_connection = websocket.create_connection(ws_url)
            cls.ws_connections[connection_key] = new_connection
            return new_connection
        except Exception as e:
            print(f"❌ Failed to create WebSocket connection: {e}")
            return None  # Explicitly return None on failure


    @classmethod
    def close_connection(cls, ws_url, node_id):
        """Close and remove a WebSocket connection."""
        connection_key = f"{ws_url}_{node_id}"
        if connection_key in cls.ws_connections:
            ws = cls.ws_connections[connection_key]
            if ws.sock and ws.sock.connected:
                ws.close()
            del cls.ws_connections[connection_key]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"ws_url": ("STRING", {}), "node_id": ("STRING", {})},  # WebSocket URL and Node ID
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image_out",)
    FUNCTION = "download_image_ws"
    CATEGORY = "oxley"

    @staticmethod
    def generate_placeholder_tensor(message="No Data"):
        """Generate a cached placeholder image tensor with a custom message."""
        if OxleyWebsocketDownloadImageNode.placeholder_tensor is not None:
            return OxleyWebsocketDownloadImageNode.placeholder_tensor  # Reuse cached tensor

        image = Image.new('RGB', (320, 240), color=(73, 109, 137))
        draw = ImageDraw.Draw(image)
        draw.text((10, 120), message, fill=(255, 255, 255))
        image_array = np.array(image).astype(np.float32) / 255.0
        image_tensor = torch.from_numpy(image_array)
        image_tensor = image_tensor[None,]  # Add batch dimension

        OxleyWebsocketDownloadImageNode.placeholder_tensor = image_tensor  # Cache
        return image_tensor
                
    def download_image_ws(self, ws_url, node_id):
        """Download image from WebSocket with optimized execution."""
        ws = self.get_connection(ws_url, node_id)
        if ws is None:
            return (self.generate_placeholder_tensor("WebSocket failed"),)
    
        try:
            message = get_latest_message(ws)
            if message is None:
                return (self.generate_placeholder_tensor("No image received"),)
    
            data = json.loads(message)
            if "image" not in data:
                return (self.generate_placeholder_tensor("No image data found"),)
    
            # ✅ Skip redundant processing if the image hasn't changed
            if hasattr(self, "last_image") and self.last_image == data["image"]:
                return (self.last_tensor,)  # ✅ Reuse last tensor if unchanged
    
            # ✅ Convert only if new
            image_data = base64.b64decode(data["image"].split(",")[1])
            image = Image.open(BytesIO(image_data)).convert("RGB")
            image_array = np.array(image).astype(np.float32) / 255.0
            image_tensor = torch.from_numpy(image_array)[None,]
    
            # ✅ Store last image and tensor
            self.last_image = data["image"]
            self.last_tensor = image_tensor
    
            return (image_tensor,)
    
        except JSONDecodeError:
            return (self.generate_placeholder_tensor("Invalid JSON"),)
        except Exception as e:
            return (self.generate_placeholder_tensor(f"Error: {e}"),)


    @classmethod
    def IS_CHANGED(cls, ws_url, node_id):
        cls.global_counter += 1
        return cls.global_counter  # Always return a unique incrementing counter
        

class OxleyWebsocketPushImageNode:
    ws_connections = {}  # Store WebSocket connections

    @classmethod
    def get_connection(cls, ws_url):
        """Ensure WebSocket connection is active"""
        try:
            if ws_url not in cls.ws_connections or not cls.ws_connections[ws_url].connected:
                cls.ws_connections[ws_url] = websocket.create_connection(ws_url)
        except Exception as e:
            print(f"Error connecting to WebSocket {ws_url}: {e}")
            raise
        return cls.ws_connections[ws_url]

    @classmethod
    def close_connection(cls, ws_url):
        """Close WebSocket connection"""
        if ws_url in cls.ws_connections:
            cls.ws_connections[ws_url].close()
            del cls.ws_connections[ws_url]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_in": ("IMAGE", {}),
                "ws_url": ("STRING", {})
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status_message",)
    FUNCTION = "push_image_ws"  # ✅ This must match the method name

    def push_image_ws(self, image_in, ws_url, format="JPEG"):
        """Push an image tensor to a WebSocket."""
        try:
            # Ensure WebSocket connection
            ws = self.get_connection(ws_url)

            # Convert tensor image to base64
            image_np = image_in.squeeze().cpu().numpy()
            if image_np.ndim == 3 and image_np.shape[0] in {1, 3}:
                image_np = image_np.transpose(1, 2, 0)

            image_np = np.clip(image_np * 255, 0, 255).astype(np.uint8)
            img = Image.fromarray(image_np)

            buffer = BytesIO()
            img.save(buffer, format=format)  # Allow format selection
            base64_string = base64.b64encode(buffer.getvalue()).decode('utf-8')

            # Send image
            ws.send(json.dumps({"image": base64_string}))

            return ("Image sent successfully",)
        except Exception as e:
            print(f"Error sending image to WebSocket: {e}")
            self.close_connection(ws_url)
            return (f"Failed to send image: {e}",)



class OxleyWebsocketReceiveJsonNode:
    ws_connections = {}
    last_known_values = {}
    last_execution_time = None
    execution_interval = timedelta(milliseconds=1000)

    @classmethod
    def get_connection(cls, ws_url, node_id):
        connection_key = f"{ws_url}_{node_id}"
        if connection_key not in cls.ws_connections:
            cls.ws_connections[connection_key] = websocket.create_connection(ws_url)
            cls.ws_connections[connection_key].settimeout(0.05)
        return cls.ws_connections[connection_key]

    @classmethod
    def close_connection(cls, ws_url, node_id):
        connection_key = f"{ws_url}_{node_id}"
        if connection_key in cls.ws_connections:
            cls.ws_connections[connection_key].close()
            del cls.ws_connections[connection_key]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ws_url": ("STRING", {}),
                "node_id": ("STRING", {}),
                "first_field_name": ("STRING", {}),
                "second_field_name": ("STRING", {}),
                "third_field_name": ("STRING", {}),
                "fourth_field_name": ("STRING", {})
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("first_field_value", "second_field_value", "third_field_value", "fourth_field_value")
    FUNCTION = "receive_json_ws"
    CATEGORY = "oxley"

    def receive_json_ws(self, ws_url, node_id, first_field_name, second_field_name, third_field_name, fourth_field_name):
        ws = self.get_connection(ws_url, node_id)
        field_names = [first_field_name, second_field_name, third_field_name, fourth_field_name]
        latest_message = None

        try:
            while True:
                try:
                    message = ws.recv()
                    if not message:
                        break
                    latest_message = message
                except websocket.WebSocketTimeoutException:
                    break
                except websocket.WebSocketException as e:
                    print(f"WebSocket error: {e}")
                    break

            if not latest_message:
                # Return last known values if they exist
                return tuple(self.last_known_values.get(fn, "N/A") for fn in field_names)

            data = json.loads(latest_message)
            # Update last known values
            for field in field_names:
                if field in data:
                    self.last_known_values[field] = data.get(field, "N/A")

            return (self.last_known_values.get(first_field_name, "N/A"),
                    self.last_known_values.get(second_field_name, "N/A"),
                    self.last_known_values.get(third_field_name, "N/A"),
                    self.last_known_values.get(fourth_field_name, "N/A"))

        except json.JSONDecodeError:
            print(f"Received non-JSON message: {latest_message}")
        except Exception as e:
            print(f"An error occurred while processing data: {e}")

        return ("Error: Non-JSON message received", "", "", "")

    @classmethod
    def IS_CHANGED(cls, ws_url, node_id, first_field_name, second_field_name, third_field_name, fourth_field_name):
        current_time = datetime.now()
        if cls.last_execution_time is None or (current_time - cls.last_execution_time) >= cls.execution_interval:
            cls.last_execution_time = current_time
            return current_time.isoformat()
        return None


class OxleyCustomNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": { "image_in" : ("IMAGE", {}) },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image_out",)
    FUNCTION = "invert"
    CATEGORY = "oxley"

    def invert(self, image_in):
        image_out = 1 - image_in
        return (image_out,)

class OxleyDownloadImageNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": { "url" : ("STRING", {}) },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image_out",)

    FUNCTION = "download_image"
    CATEGORY = "oxley"

    def download_image(self, url):
        # Send a GET request to the URL
        response = requests.get(url)
        
        # Raise an exception if the request was unsuccessful
        response.raise_for_status()

        # Open the image using Pillow
        image = Image.open(BytesIO(response.content))
        
        # Convert the image to RGB format
        image = image.convert("RGB")

        # Convert the image to a NumPy array and normalize it
        image_array = np.array(image).astype(np.float32) / 255.0

        # Convert the NumPy array to a PyTorch tensor
        image_tensor = torch.from_numpy(image_array)

        # Add a new batch dimension at the beginning
        image_tensor = image_tensor[None,]

        # Return the PyTorch tensor with the batch dimension added
        return (image_tensor,)

    @classmethod
    def IS_CHANGED(cls, url):
        # Always returns a unique value to force the node to be re-executed, e.g. returning a timestamp
        from datetime import datetime
        return datetime.now().isoformat()
