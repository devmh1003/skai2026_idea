"""계약 사이의 관계를 뽑아낸다.

계약은 한 건씩 떨어져 있는 것처럼 다루기 쉽지만 실제로는 얽혀 있다. 같은 상대방과
여러 건을 맺고 있으면 한 곳에서 틀어진 조건이 다른 계약으로 번지고, 같은 쟁점
(연대보증·국외이전 같은)이 여러 계약에 흩어져 있으면 한 번에 정리하는 편이 낫다.

두 가지 관계를 본다.

    조직 공유   같은 회사가 당사자로 들어간 계약들 — 협상 지렛대가 겹친다
    쟁점 공유   같은 쟁점이 함께 잡힌 계약들 — 같은 문안으로 함께 대응할 수 있다

계약서에서 읽어낸 것만 쓴다. 당사자 상호가 잡히지 않은 계약은 조직 관계에서 빠진다.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field

_SUFFIX = re.compile(r"(주식회사|㈜|\(주\)|법무법인|유한회사)")
_MIN_SHARED_ISSUES = 3
"""쟁점 한둘이 겹치는 것은 흔하다. 셋 이상 겹칠 때만 관계로 본다."""

_MAX_ISSUE_LINKS = 14
"""쟁점 간선은 상위만 남긴다. 다 그리면 선이 그물이 되어 아무것도 안 보인다."""


@dataclass
class Node:
    contract_id: str
    label: str
    category: str
    orgs: set[str] = field(default_factory=set)
    issues: set[str] = field(default_factory=set)


@dataclass
class Link:
    source: int
    target: int
    kind: str
    """org | issue."""

    weight: int = 1
    shared: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        head = "조직 공유" if self.kind == "org" else "쟁점 공유"
        return f"{head}: {', '.join(self.shared)}"


@dataclass
class Graph:
    nodes: list[Node] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)

    def degree(self, index: int) -> int:
        return sum(1 for link in self.links if index in (link.source, link.target))

    @property
    def org_links(self) -> list[Link]:
        return [link for link in self.links if link.kind == "org"]

    @property
    def issue_links(self) -> list[Link]:
        return [link for link in self.links if link.kind == "issue"]


def normalize_org(name: str) -> str:
    """`SK텔레콤 주식회사` 와 `주식회사 SK텔레콤` 을 같게 본다."""
    cleaned = _SUFFIX.sub(" ", name)
    return " ".join(cleaned.split()).strip()


def build(entries) -> Graph:
    """워크스페이스 계약 목록에서 관계망을 만든다."""
    graph = Graph()

    for entry in entries:
        orgs = set()
        issues = set()
        for result in entry.results:
            for party in result.parties:
                if party.name:
                    normalized = normalize_org(party.name)
                    if len(normalized) >= 2:
                        orgs.add(normalized)
            issues.update(result.category_counts())
        graph.nodes.append(
            Node(
                contract_id=entry.contract_id,
                label=entry.label,
                category=entry.category,
                orgs=orgs,
                issues=issues,
            )
        )

    issue_links: list[Link] = []
    for i, left in enumerate(graph.nodes):
        for j in range(i + 1, len(graph.nodes)):
            right = graph.nodes[j]

            shared_orgs = sorted(left.orgs & right.orgs)
            if shared_orgs:
                graph.links.append(
                    Link(i, j, "org", weight=len(shared_orgs), shared=shared_orgs)
                )
                continue  # 조직이 겹치면 그쪽이 더 강한 관계다

            shared_issues = sorted(left.issues & right.issues)
            if len(shared_issues) >= _MIN_SHARED_ISSUES:
                issue_links.append(
                    Link(i, j, "issue", weight=len(shared_issues), shared=shared_issues)
                )

    issue_links.sort(key=lambda link: -link.weight)
    graph.links.extend(issue_links[:_MAX_ISSUE_LINKS])
    return graph


def layout(graph: Graph, width: int = 760, height: int = 460, seed: int = 7) -> list[tuple[float, float]]:
    """노드 좌표를 스프링 모형으로 잡는다.

    간선은 잡아당기고 노드끼리는 밀어낸다(Fruchterman-Reingold). 브라우저에서
    물리 시뮬레이션을 돌리는 대신 여기서 계산해 좌표를 박아 넣는다 — 열 때마다
    그림이 흔들리지 않고, 자바스크립트 라이브러리도 필요 없다. 시드를 고정해
    같은 데이터면 같은 배치가 나온다.
    """
    count = len(graph.nodes)
    if count == 0:
        return []
    if count == 1:
        return [(width / 2, height / 2)]

    rng = random.Random(seed)
    margin = 90
    inner_w, inner_h = width - margin * 2, height - margin * 2

    # 초기 배치는 원형 — 무작위로 뿌리면 매듭이 생긴다.
    points = []
    for index in range(count):
        angle = 2 * math.pi * index / count
        points.append(
            [
                width / 2 + math.cos(angle) * inner_w * 0.34 + rng.uniform(-6, 6),
                height / 2 + math.sin(angle) * inner_h * 0.34 + rng.uniform(-6, 6),
            ]
        )

    area = inner_w * inner_h
    k = math.sqrt(area / count)  # 이상적인 노드 간 거리
    temperature = inner_w / 8

    for _ in range(320):
        forces = [[0.0, 0.0] for _ in range(count)]

        # 밀어내기
        for i in range(count):
            for j in range(i + 1, count):
                dx = points[i][0] - points[j][0]
                dy = points[i][1] - points[j][1]
                distance = math.hypot(dx, dy) or 0.01
                push = k * k / distance
                ux, uy = dx / distance, dy / distance
                forces[i][0] += ux * push
                forces[i][1] += uy * push
                forces[j][0] -= ux * push
                forces[j][1] -= uy * push

        # 당기기 — 관계가 강할수록 가깝게
        for link in graph.links:
            a, b = link.source, link.target
            dx = points[a][0] - points[b][0]
            dy = points[a][1] - points[b][1]
            distance = math.hypot(dx, dy) or 0.01
            pull = distance * distance / k * (1.6 if link.kind == "org" else 0.9)
            ux, uy = dx / distance, dy / distance
            forces[a][0] -= ux * pull
            forces[a][1] -= uy * pull
            forces[b][0] += ux * pull
            forces[b][1] += uy * pull

        for index in range(count):
            fx, fy = forces[index]
            magnitude = math.hypot(fx, fy) or 0.01
            step = min(magnitude, temperature)
            points[index][0] += fx / magnitude * step
            points[index][1] += fy / magnitude * step
            # 판 밖으로 나가지 않게
            points[index][0] = min(width - margin, max(margin, points[index][0]))
            points[index][1] = min(height - margin, max(margin, points[index][1]))

        temperature *= 0.965

    # 계산이 끝나면 판에 맞춰 늘린다. 그대로 두면 한쪽으로 쏠린 채 여백만 남는다.
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    span_x = max(xs) - min(xs) or 1
    span_y = max(ys) - min(ys) or 1
    scale = min(inner_w / span_x, inner_h / span_y, 1.6)
    cx = (max(xs) + min(xs)) / 2
    cy = (max(ys) + min(ys)) / 2

    return [
        (
            round(width / 2 + (x - cx) * scale, 1),
            round(height / 2 + (y - cy) * scale, 1),
        )
        for x, y in points
    ]
