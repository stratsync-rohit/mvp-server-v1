from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_database
from app.repositories.client_repository import ClientRepository
from app.schemas.client import (
    ClientCreate,
    ClientCreateResponse,
    ClientListResponse,
    ClientUpdate,
    ClientUpdateResponse,
)
from app.services.client_service import ClientService


router = APIRouter(
    prefix="/api/clients",
    tags=["Clients"]
)


def _client_data(client):
    return {
        "id": str(client["_id"]),
        "name": client["name"],
        "code": client["code"],
        "is_active": client["is_active"],
        "created_at": client["created_at"],
        "updated_at": client["updated_at"]
    }


@router.post(
    "",
    response_model=ClientCreateResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_client(
    payload: ClientCreate,
    database=Depends(get_database)
):
    try:
        repository = ClientRepository(database)
        service = ClientService(repository)

        client = await service.create_client(
            name=payload.name
        )

        return {
            "success": True,
            "data": {
                "id": str(client["_id"]),
                "name": client["name"],
                "code": client["code"],
                "is_active": client["is_active"],
                "created_at": client["created_at"],
                "updated_at": client["updated_at"]
            }
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create client"
        )


@router.get(
    "",
    response_model=ClientListResponse,
    status_code=status.HTTP_200_OK
)
async def get_clients(
    database=Depends(get_database)
):
    try:
        repository = ClientRepository(database)
        service = ClientService(repository)

        clients = await service.get_all_clients()

        return {
            "success": True,
            "data": [
                {
                    "id": str(client["_id"]),
                    "name": client["name"],
                    "code": client["code"],
                    "is_active": client["is_active"],
                    "created_at": client["created_at"],
                    "updated_at": client["updated_at"]
                }
                for client in clients
            ]
        }

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch clients"
        )    



@router.get(
    "/{client_id}",
    response_model=ClientCreateResponse,
    status_code=status.HTTP_200_OK
)
async def get_client(
    client_id: str,
    database=Depends(get_database)
):
    try:
        repository = ClientRepository(database)
        service = ClientService(repository)

        client = await service.get_client_by_id(client_id)

        return {
            "success": True,
            "data": {
                "id": str(client["_id"]),
                "name": client["name"],
                "code": client["code"],
                "is_active": client["is_active"],
                "created_at": client["created_at"],
                "updated_at": client["updated_at"]
            }
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc)
        )

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch client"
        )


@router.put(
    "/{client_id}",
    response_model=ClientUpdateResponse,
    status_code=status.HTTP_200_OK
)
async def update_client(
    client_id: str,
    payload: ClientUpdate,
    database=Depends(get_database)
):
    try:
        service = ClientService(ClientRepository(database))
        client = await service.update_client(client_id, payload)
        return {
            "success": True,
            "message": "Client updated successfully",
            "data": _client_data(client)
        }
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc)
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update client"
        )


@router.delete(
    "/{client_id}",
    response_model=ClientUpdateResponse,
    status_code=status.HTTP_200_OK,
    deprecated=True
)
async def disable_client_legacy(
    client_id: str,
    database=Depends(get_database)
):
    """Backward-compatible soft disable; no client data is deleted."""
    try:
        service = ClientService(ClientRepository(database))
        client = await service.update_client(
            client_id,
            ClientUpdate(is_active=False)
        )
        return {
            "success": True,
            "message": "Client updated successfully",
            "data": _client_data(client)
        }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to update client"
        )
