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
        while True:
            try:
                message = ws.recv()
                latest_message = message  # Update to the most recent message
            except WebSocketTimeoutException:
                break  # Exit loop if no more messages are available
    except Exception as e:
        print(f"An error occurred: {e}")
        if ws:
            ws.close()
        return -1  # Return -1 on other exceptions, indicating an error
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
    ws_connections = {}  # Class-level dictionary to store WebSocket connections by unique key
    global_counter = 0  # Global counter

    @classmethod
    def get_connection(cls, ws_url, node_id):
        """Get an existing WebSocket connection or create a new one, checking for validity."""
        connection_key = f"{ws_url}_{node_id}"
        existing_connection = cls.ws_connections.get(connection_key)
        if existing_connection:
            try:
                existing_connection.settimeout(0.1)  # Reduced timeout to 0.1 second
                existing_connection.recv()
                existing_connection.settimeout(None)  # Reset timeout as needed
                return existing_connection
            except websocket.WebSocketException:
                existing_connection.close()
                del cls.ws_connections[connection_key]

        new_connection = websocket.create_connection(ws_url)
        cls.ws_connections[connection_key] = new_connection
        return new_connection

    @classmethod
    def close_connection(cls, ws_url, node_id):
        """Close and remove a WebSocket connection."""
        connection_key = f"{ws_url}_{node_id}"
        if connection_key in cls.ws_connections:
            if cls.ws_connections[connection_key].open:
                cls.ws_connections[connection_key].close()
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
        """Generate a placeholder image with a custom message."""
        image = Image.new('RGB', (320, 240), color=(73, 109, 137))
        draw = ImageDraw.Draw(image)
        draw.text((0, 120), message, fill=(255, 255, 255))
        image_array = np.array(image).astype(np.float32) / 255.0
        image_tensor = torch.from_numpy(image_array)
        image_tensor = image_tensor[None,]  # Add batch dimension
        return image_tensor

    def download_image_ws(self, ws_url, node_id):
        # Initialize or get an existing WebSocket client connection
        ws = self.get_connection(ws_url, node_id)

        ws.settimeout(0.1)  # Reduced timeout to 0.1 second

        try:
            message = get_latest_message(ws)
            if message is None:
                return (self.generate_placeholder_tensor("No message received"),)
            elif message == -1:
                return (self.generate_placeholder_tensor("Error in WebSocket communication"),)
        except Exception as e:
            return (self.generate_placeholder_tensor(f"Error: {e}"),)

        try:
            data = json.loads(message)
            if "image" not in data:
                return (self.generate_placeholder_tensor("No image data found"),)

            image_data = base64.b64decode(data["image"].split(",")[1])
            image = Image.open(BytesIO(image_data))
            image = image.convert("RGB")
            image_array = np.array(image).astype(np.float32) / 255.0
            image_tensor = torch.from_numpy(image_array)
            image_tensor = image_tensor[None,]
            return (image_tensor,)
        except JSONDecodeError:
            return (self.generate_placeholder_tensor("Invalid JSON received"),)
        except Exception as e:
            return (self.generate_placeholder_tensor(f"Error processing image: {e}"),)

    @classmethod
    def IS_CHANGED(cls, ws_url, node_id):
        cls.global_counter += 1
        return cls.global_counter  # Always return a unique incrementing counter
        

class OxleyWebsocketPushImageNode:
    ws_connections = {}  # Class-level dictionary to store WebSocket connections by URL

    @classmethod
    def get_connection(cls, ws_url):
        """Get an existing WebSocket connection or create a new one."""
        try:
            if ws_url not in cls.ws_connections or not cls.ws_connections[ws_url].connected:
                cls.ws_connections[ws_url] = websocket.create_connection(ws_url)
        except Exception as e:
            print(f"Error connecting to WebSocket {ws_url}: {e}")
            # logging.error(f"Error connecting to WebSocket {ws_url}: {e}")
            # Here, decide whether to retry, raise an exception, or handle the error differently.
            raise
        return cls.ws_connections[ws_url]

    @classmethod
    def close_connection(cls, ws_url):
        """Close and remove a WebSocket connection."""
        if ws_url in cls.ws_connections:
            cls.ws_connections[ws_url].close()
            del cls.ws_connections[ws_url]
            
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_in": ("IMAGE", {}),  # Input image
                "ws_url": ("STRING", {})    # WebSocket URL to push the image to
            },
        }

    RETURN_TYPES = ("STRING",)  # Possible return type for confirmation/message
    RETURN_NAMES = ("status_message",)
    FUNCTION = "push_image_ws"
    CATEGORY = "oxley"

    def push_image_ws(self, image_in, ws_url):
        # Assuming image_in is a PyTorch tensor with shape [1, C, H, W] or similar
        
        # Remove unnecessary dimensions and ensure the tensor is CPU-bound
        image_np = image_in.squeeze().cpu().numpy()
        
        # If your tensor has a shape [C, H, W] (common in PyTorch), convert it to [H, W, C]
        if image_np.ndim == 3 and image_np.shape[0] in {1, 3}:
            # This assumes a 3-channel (RGB) or 1-channel (grayscale) image.
            # Adjust the transpose for different formats if necessary.
            image_np = image_np.transpose(1, 2, 0)
        
        # The tensor should now be in a shape compatible with PIL (H, W, C)
        # For grayscale images (with no color channel), this step isn't necessary.
        
        # Convert numpy array to uint8 if not already
        image_np = np.clip(image_np * 255, 0, 255).astype(np.uint8)
        
        try:
            img = Image.fromarray(image_np)
        except TypeError as e:
            raise ValueError(f"Failed to convert array to image: {e}")

        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        jpeg_bytes = buffer.getvalue()
        base64_bytes = base64.b64encode(jpeg_bytes)
        base64_string = base64_bytes.decode('utf-8')

        try:
            # Initialize or get an existing WebSocket client connection
            ws = self.get_connection(ws_url)
    
            # Prepare the message
            message = json.dumps({"image": base64_string})
    
            # Send the message
            ws.send(message)
            
            return ("Image sent successfully",)
        except ssl.SSLError as ssl_error:
            print(f"SSL error when sending image to {ws_url}: {ssl_error}")
            self.close_connection(ws_url)  # Close the problematic connection
            # Handle the error further or retry as needed.
        except Exception as ex:
            print(f"An error occurred when sending image to {ws_url}: {ex}")
            self.close_connection(ws_url)  # Close the problematic connection
            # Decide how to handle unexpected errors: retry, raise, etc.
        
        return ("Image sent successfully",)

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
