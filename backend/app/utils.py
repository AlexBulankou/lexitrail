from flask import request, jsonify
import base64
import logging

# Define ANSI color codes
BLUE = '\033[94m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

logger = logging.getLogger(__name__)

class ColorTruncatingFormatter(logging.Formatter):
    def __init__(self, fmt: str, max_length: int = 100):
        super().__init__(fmt)
        self.max_length = max_length

    def format(self, record: logging.LogRecord) -> str:
        # Color the timestamp blue, including the brackets
        record.asctime = f"{BLUE}[{self.formatTime(record)}]{RESET}"
        
        # Color based on log level
        if record.levelno >= logging.ERROR:
            record.levelname = f"{RED}{record.levelname}{RESET}"
        elif record.levelno >= logging.WARNING:
            record.levelname = f"{YELLOW}{record.levelname}{RESET}"
            
        # Process the arguments if they exist
        if record.args:
            processed_args = []
            for arg in record.args:
                if isinstance(arg, (bytes, bytearray)):
                    processed_args.append(f"<binary data of length {len(arg)}>")
                elif isinstance(arg, str) and record.levelno <= logging.INFO:  # Only truncate for INFO and DEBUG
                    processed_args.append(arg[:self.max_length] + "..." if len(arg) > self.max_length else arg)
                else:
                    processed_args.append(arg)
            record.args = tuple(processed_args)
            
        # Truncate the message if it's too long, but only for INFO and DEBUG levels
        if isinstance(record.msg, (bytes, bytearray)):
            record.msg = f"<binary data of length {len(record.msg)}>"
        elif isinstance(record.msg, str):
            if record.levelno <= logging.INFO:  # Only truncate for INFO and DEBUG
                # Split message into parts by comma and handle each part
                parts = str(record.msg).split(',')
                processed_parts = []
                for part in parts:
                    # If part contains binary data indicator, keep it short
                    if 'hint_img=' in part and 'b\'' in part:
                        processed_parts.append('hint_img=<binary data>')
                    else:
                        if len(part) > self.max_length:
                            processed_parts.append(part[:self.max_length] + "...")
                        else:
                            processed_parts.append(part)
                record.msg = ','.join(processed_parts)
            
        return super().format(record)

def to_dict(model_instance):
    """
    Convert SQLAlchemy model instance to dictionary.
    Handles binary fields by excluding them or converting appropriately.
    """
    result = {}
    for c in model_instance.__table__.columns:
        value = getattr(model_instance, c.name)
        if isinstance(value, bytes):
            # Skip binary fields like hint_img or encode them
            result[c.name] = base64.b64encode(value).decode('utf-8') if c.name == 'hint_img' else None
        else:
            result[c.name] = value
    return result


def not_found_response(message="Resource not found"):
    """
    Returns a standardized JSON response for 404 errors.
    """
    response = jsonify({"error": message})
    response.status_code = 404
    return response

def success_response(data, message=None, **additional_data):
    """
    Creates a success response with optional additional data.
    The original data is always included in the 'data' field to maintain compatibility.
    Additional metadata can be included without affecting existing clients.
    
    Args:
        data: The main response data
        message: Optional success message
        **additional_data: Optional additional data fields to include in response
    """
    response = {
        "success": True,
        "data": data
    }
    
    if message:
        response["message"] = message
        
    # Add any additional data fields
    response.update(additional_data)
    
    # Log the success response with truncated data
    data_str = str(data)
    truncated_data = (data_str[:97] + '...') if len(data_str) > 100 else data_str
    log_message = f"Success response sent: {message if message else 'No message'} | Data: {truncated_data}"
    if additional_data:
        log_message += f" | Additional data: {additional_data}"
    logger.info(log_message)
    
    return response

def error_response(message, status_code=400, **additional_data):
    """
    Creates an error response with optional additional data.
    The error message is always included in the 'message' field to maintain compatibility.
    Additional metadata can be included without affecting existing clients.
    
    Args:
        message: The error message
        status_code: HTTP status code (default: 400)
        **additional_data: Optional additional data fields to include in response
    """
    response = {
        "success": False,
        "message": str(message)
    }
    
    # Add any additional data fields
    response.update(additional_data)
    
    # Log the error response
    log_message = f"Error response sent (status {status_code}): {message}"
    if additional_data:
        log_message += f" | Additional data: {additional_data}"
    logger.error(log_message)
    
    return response, status_code

def validate_user_access(email):
    authenticated_email = request.user['email']

    # Log debug information for authenticated user
    logging.info(f"Authenticated user: {request.user['email']} accessing user: {email}")

    # Check if the authenticated user is trying to access their own data
    if authenticated_email != email:
        return jsonify({"message": "Unauthorized: You can only access your own data"}), 403

    # If the user is authorized, return None to allow the request to proceed
    return None
