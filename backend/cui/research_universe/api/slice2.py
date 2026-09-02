"""Native Slice 2 sealed PARK contract."""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import Field
from cui.research_universe.api.routes import LibraryContext, LocalPrincipal
from cui.research_universe.api.slice1 import Command, CommandResponse, _active, _universe_for_workspace
from cui.research_universe.application import Slice1Service, NotFound, BoundaryViolation, park_release_refs, workspace_projection
from cui.research_universe.store.event_store import ExpectedSequenceConflict, CommandFingerprintConflict, UniverseNotFound
class CaptureCommand(Command): original_text:str=Field(min_length=1)
class ReleaseCommand(Command):
 provisional_role:Literal["trigger_question","exploration_context","material_lead","unnamed"]; workspace_id:str|None=None; question:str|None=Field(default=None,min_length=1); workspace_expected_sequence:int=Field(default=0,ge=0)
class ForgeCommand(Command): claim_id:str; capture_id:str; release_id:str
def create_slice2_router(service,store,sealed_store,context:LibraryContext,principal:LocalPrincipal)->APIRouter:
 router=APIRouter(tags=["research-universe-slice2-park"])
 def fail(e):
  if isinstance(e,ExpectedSequenceConflict): raise HTTPException(409,"stale expected_sequence")
  if isinstance(e,CommandFingerprintConflict): raise HTTPException(409,"command_id reused with different semantic command")
  if isinstance(e,(NotFound,UniverseNotFound)): raise HTTPException(404,str(e))
  if isinstance(e,BoundaryViolation): raise HTTPException(422,str(e))
  raise e
 def detail(cap):
  universe_ids=store.list_universes_for_library(context.library_id,include_archived=True)
  refs=[ref for uid in universe_ids for ref in park_release_refs(store,uid,cap.id)]
  forged=[{"universe_id":uid,"id":p.provenance_id,"claim_id":p.claim_id,"capture_id":p.capture_id,"release_id":p.release_id,"workspace_id":p.workspace_id} for uid in universe_ids for e in store.read_events(uid) if e.event_type=="claim_forged_from_capture" and (p:=e.validated_payload()).capture_id==cap.id]
  return {"id":cap.id,"original_text":cap.original_text,"status":"sealed","released":bool(refs),"releases":refs,"forged_into":forged}
 def summary(cap):
  data=detail(cap)
  return {key:value for key,value in data.items() if key != "original_text"}
 @router.post("/park-captures",status_code=status.HTTP_201_CREATED,response_model=CommandResponse)
 def capture(body:CaptureCommand):
  try:
   r=sealed_store.capture(context.library_id,body.command_id,body.expected_sequence,body.original_text); return CommandResponse(commit_position=0,event_ids=[],result=r.result_payload,fragment=detail(sealed_store.get(context.library_id,r.capture_id)))
  except Exception as e: fail(e)
 @router.get("/park-captures")
 def captures(): return {"library_id":context.library_id,"captures":[summary(x) for x in sealed_store.list(context.library_id)]}
 @router.get("/park-captures/{capture_id}")
 def get(capture_id:str):
  cap=sealed_store.get(context.library_id,capture_id)
  if cap is None: raise HTTPException(404,"capture not in active library")
  return detail(cap)
 @router.post("/park-captures/{capture_id}/release",response_model=CommandResponse)
 def release(capture_id:str,body:ReleaseCommand):
  if sealed_store.get(context.library_id,capture_id) is None: raise HTTPException(404,"capture not in active library")
  uid=_active(store,context)
  if body.workspace_id is not None: _universe_for_workspace(store,context,body.workspace_id)
  try:
   r=service.release_park(uid,capture_id,body.command_id,body.expected_sequence,body.provisional_role,body.workspace_id,body.question,body.workspace_expected_sequence); return CommandResponse(commit_position=r.commit_position,event_ids=r.event_ids,result=r.result_payload,fragment=workspace_projection(store,uid,r.result_payload["workspace_id"]))
  except Exception as e: fail(e)
 @router.post("/workspaces/{workspace_id}/claims/forge-provenance",response_model=CommandResponse)
 def forge(workspace_id:str,body:ForgeCommand):
  if sealed_store.get(context.library_id,body.capture_id) is None: raise HTTPException(404,"capture not in active library")
  uid=_universe_for_workspace(store,context,workspace_id)
  try:
   r=service.forge_claim_from_capture(uid,workspace_id,body.claim_id,body.capture_id,body.release_id,body.command_id,body.expected_sequence); return CommandResponse(commit_position=r.commit_position,event_ids=r.event_ids,result=r.result_payload,fragment=workspace_projection(store,uid,workspace_id))
  except Exception as e: fail(e)
 return router
