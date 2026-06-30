from typing import NamedTuple

from bs4 import BeautifulSoup, Tag


class SemanticBlock(NamedTuple):
    """Represents a self-contained semantic block found in the DOM."""

    element: Tag
    block_type: str
    title: str | None
    content_text: str


class LabelValuePair(NamedTuple):
    """A compact fact represented by adjacent label/value DOM siblings."""

    label: str
    value: str
    container: Tag


class DomEntityExtractor:
    """
    A "container-aware" extractor that identifies and extracts semantic blocks
    (like product cards, FAQ items, etc.) from a DOM structure.

    This aligns with the goal to "Preserve entity boundaries before chunking"
    from the project's TODO files.

    # TODO [GraphRAG – SemanticBlock as named entity node]:
    # Each SemanticBlock with a non-null `title` is a strong candidate for a
    # named entity node in the knowledge graph (e.g. VehicleCard:"VF 9 Plus").
    # `extract_semantic_blocks()` should optionally return a list of graph node
    # descriptors (node_id, label, properties) alongside the SemanticBlock list
    # so the graph import layer can consume them without re-parsing the DOM.
    # Suggested node schema: {node_id: block_id, label: block_type, name: title,
    #   source_url: url, ingested_at: timestamp}.
    # Reference: GraphRAG integration plan (to be created)
    """

    def __init__(self, soup: BeautifulSoup):
        self.soup = soup

    def extract_semantic_blocks(
        self, container_selector: str, title_selector: str | None = None
    ) -> list[SemanticBlock]:
        """
        Extracts semantic blocks from the DOM based on a container selector.

        Args:
            container_selector: A CSS selector to identify the parent container
                for each semantic block (e.g., 'article.faq-item').
            title_selector: An optional CSS selector to find the title within
                each container.

        Returns:
            A list of SemanticBlock objects.
        """
        blocks: list[SemanticBlock] = []
        containers = self.soup.select(container_selector)

        for container in containers:
            title_element = container.select_one(title_selector) if title_selector else None
            title = title_element.get_text(strip=True) if title_element else None
            content_text = container.get_text(strip=True)

            blocks.append(
                SemanticBlock(
                    element=container,
                    block_type="entity_card",  # Generic type, can be refined
                    title=title,
                    content_text=content_text,
                )
            )
        return blocks

    def extract_label_value_pairs(
        self,
        container_selector: str = "body",
    ) -> list[LabelValuePair]:
        """Extract adjacent label/value facts from grid or flexbox markup.

        # TODO [GraphRAG – LabelValuePair as HAS_ATTRIBUTE graph edge]:
        # Each LabelValuePair (label, value) extracted from a DOM container is a
        # structured fact that maps naturally to a property graph edge:
        #   (EntityNode)-[:HAS_ATTRIBUTE {name: label, value: value}]->(ValueNode)
        # When the graph layer is introduced, pipe these pairs through a
        # `label_value_to_graph_edge()` adapter that resolves the parent entity
        # node from the container's block_id before writing to the graph store.
        # Reference: GraphRAG integration plan (to be created)
        """

        pairs: list[LabelValuePair] = []
        for container in self.soup.select(container_selector):
            children = [
                child for child in container.find_all(recursive=False) if isinstance(child, Tag)
            ]
            index = 0
            while index + 1 < len(children):
                label = _clean_text(children[index])
                value = _clean_text(children[index + 1])
                if _looks_like_label_value_pair(label, value):
                    pair = LabelValuePair(label=label, value=value, container=container)
                    if pair not in pairs:
                        pairs.append(pair)
                    index += 2
                    continue
                index += 1
        return pairs


def _clean_text(element: Tag) -> str:
    return " ".join(element.get_text(" ", strip=True).split())


def _looks_like_label_value_pair(label: str, value: str) -> bool:
    if not label or not value:
        return False
    if len(label) > 80 or len(value) > 160:
        return False
    if label == value:
        return False
    value_lower = value.casefold()
    return any(
        marker in value_lower
        for marker in ("km", "kwh", "kw", "nm", "vnd", "vnđ", "₫", "mm", "giây", "phút")
    ) or any(char.isdigit() for char in value)
