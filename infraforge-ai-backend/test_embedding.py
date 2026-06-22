from app.ai.embedding_service import generate_embedding

embedding = generate_embedding("Excavator machine")

print(embedding)
print(len(embedding))