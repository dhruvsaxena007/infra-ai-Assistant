def success_response(
    message: str = "Success",
    data=None
):
    return {
        "success": True,
        "message": message,
        "data": data if data is not None else {},
        "error": None
    }


def error_response(
    message: str = "Something went wrong",
    error=None
):
    return {
        "success": False,
        "message": message,
        "data": {},
        "error": error
    }