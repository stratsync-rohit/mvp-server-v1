import re
from bson import ObjectId

from app.schemas.client import ClientUpdate


class ClientService:

    def __init__(self, client_repository):
         self.client_repository = client_repository
 
 
    async def create_client(self, name: str):

       
        name = name.strip()

       
        clean_name = re.sub(r"[^A-Za-z0-9]", "", name)

        prefix = clean_name[:3].upper()

       
        if len(prefix) < 2:
            raise ValueError("Invalid client name")

        
        number = 1

        while True:
            code = f"{prefix}-{number:03d}"

            existing_client = await self.client_repository.get_by_code(code)

            if existing_client is None:
                break

            number += 1

       
        client = await self.client_repository.create_client(
            name=name,
            code=code
        )

        return client

    async def get_client_by_id(self, client_id: str):
        client = await self.client_repository.get_client_by_id(client_id)

        if client is None:
            raise ValueError("Client not found")

        return client


    async def get_all_clients(self):
        clients = await self.client_repository.get_all_clients()
        return clients

    async def update_client(
        self,
        client_id: str,
        update_data: ClientUpdate
    ):
        if not ObjectId.is_valid(client_id):
            raise ValueError("Invalid client ID")

        existing_client = await self.client_repository.get_client_by_id(client_id)
        if existing_client is None:
            raise LookupError("Client not found")

        updates = update_data.model_dump(exclude_unset=True)
        if "name" in updates:
            updates["name"] = updates["name"].strip()

        updated_client = await self.client_repository.update_client(
            ObjectId(client_id), updates
        )
        if updated_client is None:
            raise LookupError("Client not found")
        return updated_client
    
    
