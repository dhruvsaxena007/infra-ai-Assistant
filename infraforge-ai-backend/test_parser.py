from app.ai.query_parser import parse_query

query = "excavator in delhi under 8000"

result = parse_query(query)

print(result)