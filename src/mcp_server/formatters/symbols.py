from typing import Dict, List, Any

def format_symbol_context(context: Dict) -> str:
    """Format symbol context for ChatGPT display."""
    symbol = context["symbol"]
    location = context["location"]

    formatted = [
        f"## {symbol['name']} ({symbol['kind']})\n\n",
        f"**Location**: {location['repository']}/{location['file']} (lines {location['lines']})\n\n",
        f"**IDs**: symbol_id={symbol['id']}, file_id={symbol['file_id']}, repository_id={symbol['repository_id']}\n\n",
        f"**Signature**: `{symbol['signature']}`\n\n",
    ]

    if symbol["documentation"]:
        formatted.append(f"**Documentation**: {symbol['documentation']}\n\n")

    if symbol["parameters"]:
        formatted.append("**Parameters**:\n")
        for param in symbol["parameters"]:
            param_type = (
                param.get("type", "unknown")
                if isinstance(param, dict)
                else "unknown"
            )
            param_name = (
                param.get("name", str(param))
                if isinstance(param, dict)
                else str(param)
            )
            formatted.append(f"- `{param_name}`: {param_type}\n")
        formatted.append("\n")

    if symbol["return_type"]:
        formatted.append(f"**Returns**: {symbol['return_type']}\n\n")

    if symbol["complexity"]:
        formatted.append(f"**Complexity**: {symbol['complexity']}\n\n")

    # Add relationships if present
    if "relationships" in context:
        rels = context["relationships"]
        if any(rels.values()):
            formatted.append("**Relationships**:\n\n")

            if rels["calls"]:
                formatted.append("*Calls*:\n")
                for rel in rels["calls"]:
                    formatted.append(
                        f"- {rel['name']} (ID: {rel['id']}, {rel['kind']})\n"
                    )
                formatted.append("\n")

            if rels["called_by"]:
                formatted.append("*Called by*:\n")
                for rel in rels["called_by"]:
                    formatted.append(
                        f"- {rel['name']} (ID: {rel['id']}, {rel['kind']})\n"
                    )
                formatted.append("\n")

            if rels["inherits_from"]:
                formatted.append("*Inherits from*:\n")
                for rel in rels["inherits_from"]:
                    formatted.append(
                        f"- {rel['name']} (ID: {rel['id']}, {rel['kind']})\n"
                    )
                formatted.append("\n")

            if rels["inherited_by"]:
                formatted.append("*Inherited by*:\n")
                for rel in rels["inherited_by"]:
                    formatted.append(
                        f"- {rel['name']} (ID: {rel['id']}, {rel['kind']})\n"
                    )
                formatted.append("\n")

    # Add source code if available
    if "source_code" in context:
        formatted.append("**Source Code**:\n")
        formatted.append(f"```{location['language']}\n")
        formatted.append(context["source_code"])
        formatted.append("\n```\n\n")

    # Add connected endpoints (Phase 3: The Linker)
    if "connected_endpoints" in context:
        conn = context["connected_endpoints"]
        if any(conn.values()):
            formatted.append("**Connected Endpoints (Cross-Service)**:\n\n")
            
            # Outgoing API calls
            if conn.get("outgoing_api_calls"):
                formatted.append("*Outgoing API Calls*:\n")
                for call in conn["outgoing_api_calls"]:
                    formatted.append(
                        f"- `{call['http_method']} {call['url_pattern']}`"
                    )
                    if call.get("linked_endpoint"):
                        ep = call["linked_endpoint"]
                        formatted.append(
                            f" → **{ep['name']}** in `{ep['repository']}`"
                            f" (confidence: {ep['match_confidence']}%)"
                        )
                    formatted.append("\n")
                formatted.append("\n")
            
            # Incoming API calls
            if conn.get("incoming_api_calls"):
                formatted.append("*Called By (Cross-Service)*:\n")
                for call in conn["incoming_api_calls"]:
                    formatted.append(
                        f"- `{call['http_method']} {call['url_pattern']}` "
                        f"from `{call['source_repository']}` "
                        f"(confidence: {call['match_confidence']}%)\n"
                    )
                formatted.append("\n")
            
            # Published events
            if conn.get("published_events"):
                formatted.append("*Publishes Events*:\n")
                for event in conn["published_events"]:
                    formatted.append(f"- **{event['event_type']}**")
                    if event.get("topic"):
                        formatted.append(f" to `{event['topic']}`")
                    if event.get("subscribers"):
                        subs = event["subscribers"]
                        formatted.append(f" ({len(subs)} subscriber(s))")
                    formatted.append("\n")
                formatted.append("\n")
            
            # Subscribed events
            if conn.get("subscribed_events"):
                formatted.append("*Subscribes To Events*:\n")
                for sub in conn["subscribed_events"]:
                    formatted.append(f"- **{sub['event_type']}**")
                    if sub.get("queue"):
                        formatted.append(f" via `{sub['queue']}`")
                    if sub.get("publishers"):
                        pubs = sub["publishers"]
                        formatted.append(f" ({len(pubs)} publisher(s))")
                    formatted.append("\n")
                formatted.append("\n")

    return "".join(formatted)
