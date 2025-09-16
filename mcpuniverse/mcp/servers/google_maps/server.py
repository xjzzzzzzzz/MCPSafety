"""
Google Maps MCP Server

This server provides tools for interacting with Google Maps APIs including:
- Geocoding and reverse geocoding
- Place search and details
- Distance matrix calculations
- Elevation data
- Directions
"""
# pylint: disable=broad-exception-caught
import json
import os
from typing import Any, Dict, List, Optional

import click
import httpx
from mcp.server.fastmcp import FastMCP
from mcpuniverse.common.logger import get_logger


def get_api_key() -> str:
    """Get Google Maps API key from environment variables."""
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY environment variable is not set")
    return api_key


async def make_request(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Make HTTP request to Google Maps API."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()  
            return response.json()
    except httpx.HTTPStatusError as e:
        return {
            "status": "ERROR",
            "error_message": f"HTTP {e.response.status_code}: {e.response.text}"
        }
    except httpx.RequestError as e:
        return {
            "status": "ERROR", 
            "error_message": f"Request failed: {str(e)}"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": f"Unexpected error: {str(e)}"
        }


def build_server(port: int) -> FastMCP:
    """
    Initializes the MCP server.

    :param port: Port for SSE.
    :return: The MCP server.
    """
    mcp = FastMCP("google-maps", port=port)
    api_key = get_api_key()

    @mcp.tool()
    async def maps_geocode(address: str) -> str:
        """
        Convert an address into geographic coordinates.
        
        Args:
            address: The address to geocode
            
        Returns:
            JSON string with location, formatted_address, and place_id
        """
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address,
            "key": api_key
        }
        
        data = await make_request(url, params)
        
        if data.get("status") != "OK":
            return json.dumps({
                "error": f"Geocoding failed: {data.get('error_message', data.get('status'))}"
            })
        
        result = data["results"][0]
        return json.dumps({
            "location": result["geometry"]["location"],
            "formatted_address": result["formatted_address"],
            "place_id": result["place_id"]
        }, indent=2)

    @mcp.tool()
    async def maps_reverse_geocode(latitude: float, longitude: float) -> str:
        """
        Convert coordinates into an address.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            JSON string with formatted_address, place_id, and address_components
        """
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "latlng": f"{latitude},{longitude}",
            "key": api_key
        }
        
        data = await make_request(url, params)
        
        if data.get("status") != "OK":
            return json.dumps({
                "error": f"Reverse geocoding failed: {data.get('error_message', data.get('status'))}"
            })
        
        result = data["results"][0]
        return json.dumps({
            "formatted_address": result["formatted_address"],
            "place_id": result["place_id"],
            "address_components": result["address_components"]
        }, indent=2)

    @mcp.tool()
    async def maps_search_places(query: str, location: Optional[Dict] = None, radius: Optional[int] = None) -> str:
        """
        Search for places using Google Places API.
        
        Args:
            query: Search query
            location: Optional center point for the search (dict with latitude and longitude)
            radius: Search radius in meters (max 50000)
            
        Returns:
            JSON string with list of places
        """
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {
            "query": query,
            "key": api_key
        }
        
        if location:
            params["location"] = f"{location['latitude']},{location['longitude']}"
        if radius:
            params["radius"] = str(radius)
        
        data = await make_request(url, params)
        
        if data.get("status") != "OK":
            return json.dumps({
                "error": f"Place search failed: {data.get('error_message', data.get('status'))}"
            })
        
        places = []
        for place in data["results"]:
            places.append({
                "name": place["name"],
                "formatted_address": place["formatted_address"],
                "location": place["geometry"]["location"],
                "place_id": place["place_id"],
                "rating": place.get("rating"),
                "types": place.get("types", [])
            })
        
        return json.dumps({"places": places}, indent=2)

    @mcp.tool()
    async def maps_place_details(place_id: str) -> str:
        """
        Get detailed information about a specific place.
        
        Args:
            place_id: The place ID to get details for
            
        Returns:
            JSON string with place details
        """
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            "place_id": place_id,
            "key": api_key
        }
        
        data = await make_request(url, params)
        
        if data.get("status") != "OK":
            return json.dumps({
                "error": f"Place details request failed: {data.get('error_message', data.get('status'))}"
            })
        
        result = data["result"]
        return json.dumps({
            "name": result["name"],
            "formatted_address": result["formatted_address"],
            "location": result["geometry"]["location"],
            "formatted_phone_number": result.get("formatted_phone_number"),
            "website": result.get("website"),
            "rating": result.get("rating"),
            "reviews": result.get("reviews", []),
            "opening_hours": result.get("opening_hours")
        }, indent=2)

    @mcp.tool()
    async def maps_distance_matrix(origins: List[str], destinations: List[str], mode: str = "driving") -> str:
        """
        Calculate travel distance and time for multiple origins and destinations.
        
        Args:
            origins: Array of origin addresses or coordinates
            destinations: Array of destination addresses or coordinates
            mode: Travel mode (driving, walking, bicycling, transit)
            
        Returns:
            JSON string with distance matrix results
        """
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": "|".join(origins),
            "destinations": "|".join(destinations),
            "mode": mode,
            "key": api_key
        }
        
        data = await make_request(url, params)
        
        if data.get("status") != "OK":
            return json.dumps({
                "error": f"Distance matrix request failed: {data.get('error_message', data.get('status'))}"
            })
        
        results = []
        for row in data["rows"]:
            elements = []
            for element in row["elements"]:
                elements.append({
                    "status": element["status"],
                    "duration": element.get("duration"),
                    "distance": element.get("distance")
                })
            results.append({"elements": elements})
        
        return json.dumps({
            "origin_addresses": data["origin_addresses"],
            "destination_addresses": data["destination_addresses"],
            "results": results
        }, indent=2)

    @mcp.tool()
    async def maps_elevation(locations: List[Dict[str, float]]) -> str:
        """
        Get elevation data for locations on the earth.
        
        Args:
            locations: Array of locations with latitude and longitude
            
        Returns:
            JSON string with elevation data
        """
        url = "https://maps.googleapis.com/maps/api/elevation/json"
        location_string = "|".join([f"{loc['latitude']},{loc['longitude']}" for loc in locations])
        params = {
            "locations": location_string,
            "key": api_key
        }
        
        data = await make_request(url, params)
        
        if data.get("status") != "OK":
            return json.dumps({
                "error": f"Elevation request failed: {data.get('error_message', data.get('status'))}"
            })
        
        results = []
        for result in data["results"]:
            results.append({
                "elevation": result["elevation"],
                "location": result["location"],
                "resolution": result["resolution"]
            })
        
        return json.dumps({"results": results}, indent=2)

    @mcp.tool()
    async def maps_directions(origin: str, destination: str, mode: str = "driving") -> str:
        """
        Get directions between two points.
        
        Args:
            origin: Starting point address or coordinates
            destination: Ending point address or coordinates
            mode: Travel mode (driving, walking, bicycling, transit)
            
        Returns:
            JSON string with directions
        """
        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "key": api_key
        }
        
        data = await make_request(url, params)
        routes = []
        if data.get("status") != "OK":
            return json.dumps({
                "error": f"Directions request failed: {data.get('error_message', data.get('status'))}"
            })
        
        
        for route in data["routes"]:
            leg = route["legs"][0]
            steps = []
            for step in leg["steps"]:
                steps.append({
                    "instructions": step["html_instructions"],
                    "distance": step["distance"],
                    "duration": step["duration"],
                    "travel_mode": step["travel_mode"]
                })
            
            routes.append({
                "summary": route["summary"],
                "distance": leg["distance"],
                "duration": leg["duration"],
                "steps": steps
            })
        
        return json.dumps({"routes": routes}, indent=2)

    return mcp


@click.command()
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="Transport type",
)
@click.option("--port", default="8000", help="Port to listen on for SSE")
def main(transport: str, port: str):
    """
    Starts the initialized MCP server.

    :param port: Port for SSE.
    :param transport: The transport type, e.g., `stdio` or `sse`.
    :return:
    """
    assert transport.lower() in ["stdio", "sse"], \
        "Transport should be `stdio` or `sse`"
    logger = get_logger("Service:google_maps")
    logger.info("Starting the MCP Google Maps server")
    mcp = build_server(int(port))
    mcp.run(transport=transport.lower())