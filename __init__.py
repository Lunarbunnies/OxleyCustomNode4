from .oxleycustomnode import OxleyCustomNode, OxleyDownloadImageNode, OxleyWebsocketDownloadImageNode, OxleyWebsocketReceiveJsonNode, OxleyWebsocketPushImageNode, OxleyAlternatorNode

# Mapping of node class names to their corresponding classes
NODE_CLASS_MAPPINGS = {
    "oxleycustomnode": OxleyCustomNode,
    "oxleydownloadimagenode": OxleyDownloadImageNode,
    "oxleywebsocketdownloadimagenode": OxleyWebsocketDownloadImageNode,
    "oxleywebsocketpushimagenode": OxleyWebsocketPushImageNode,
    "oxleywebsocketreceivejsonnode": OxleyWebsocketReceiveJsonNode,
    "oxleyalternatornode": OxleyAlternatorNode 
}

# Mapping of node class names to their display names in the UI
NODE_DISPLAY_NAME_MAPPINGS = {
    "oxleycustomnode": "Oxley Image Inverter",
    "oxleydownloadimagenode": "Oxley Image Downloader", 
    "oxleywebsocketdownloadimagenode": "Oxley Image Websocket Downloader", 
    "oxleywebsocketpushimagenode": "Oxley Image Websocket Uploader",     
    "oxleywebsocketreceivejsonnode": "Oxley Json Websocket Downloader",
    "oxleyalternatornode": "Oxley Alternator" 
}

# List of symbols that are imported when 'from package import *' is used
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
