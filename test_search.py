import asyncio
from src.search_utils import search_specification

async def main():
    # Example usage
    supplier = "Example Supplier"
    part_numbers = ["ABC123"]
    specifications = [
        "Dimensions",
        "Weight",
        "Material"
    ]
    
    try:
        results = await search_specification(supplier, part_numbers, specifications)
        print("Search Results:")
        print(results)
    except Exception as e:
        print(f"Error occurred: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 