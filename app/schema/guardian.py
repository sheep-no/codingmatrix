from pydantic import BaseModel
class StartGuard(BaseModel):
    service_name:str
    port:int
    restart_cmd:str