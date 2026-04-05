
def on_join_job_room(data, socket):
    """
    Mobile emits: socket.emit("join_job_room", {"job": "JOB-XXX"})
    Server adds that socket to room "job:{job}" so it receives job_message events.
    """
    job = (data or {}).get("job")
    if not job:
        return
    socket.join(f"job:{job}")