
def on_join_job_room(data, socket):
    """
    Mobile emits: socket.emit("join_job_room", {"job": "JOB-XXX"})
    Server adds that socket to room "job:{job}" so it receives job_message events.
    """
    job = (data or {}).get("job")
    if not job:
        return
    socket.join(f"job:{job}")


def on_leave_job_room(data, socket):
    """
    Mobile emits: socket.emit("leave_job_room", {"job": "JOB-XXX"})
    Server removes that socket from the room when the chat screen is closed.
    """
    job = (data or {}).get("job")
    if not job:
        return
    socket.leave(f"job:{job}")