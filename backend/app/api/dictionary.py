from fastapi import APIRouter, HTTPException, Query

from app.services import dictionary

router = APIRouter(prefix="/api", tags=["dictionary"])


@router.get("/dictionary", response_model=dictionary.DictionaryEntry)
def lookup_word(word: str = Query(..., min_length=1), language: str = Query(...)):
    entry = dictionary.lookup_word(word, language)
    if entry is None:
        raise HTTPException(status_code=404, detail="No definition found")
    return entry
