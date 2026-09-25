import os
import pickle
from typing import Optional
from fastapi import APIRouter, Request

from core import YumeApp
from helpers.daily import refresh_daily_limits
from helpers.master_data import master_data_manifest
from helpers.msgpack import read_request, respond
from helpers.user_data import current_user_id, user_data
from models import *

router = APIRouter(tags=["Data"])

@router.get("/api/data/master", name="Data_GetMasterData")
async def data_get_master_data(request: Request):
    app: YumeApp = request.app
    return respond(master_data_manifest())

@router.get("/api/data/user", name="Data_GetUserData")
async def data_get_user_data(request: Request):
    print("\n[API BYPASS] Intercepting /api/data/user, serving raw backup...")
    try:
        pkl_path = os.path.join(os.getcwd(), 'scraped_account.pkl')
        with open(pkl_path, 'rb') as f:
            scraped_data = pickle.load(f)
        return respond(scraped_data)
    except Exception as e:
        print(f"[API BYPASS FAILED] {e}. Falling back to local DB.")
        app: YumeApp = request.app
        user_id = current_user_id(request)
        await refresh_daily_limits(app, user_id)
        return respond(await user_data(app, user_id))
