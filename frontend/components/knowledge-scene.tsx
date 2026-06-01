"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

const NODE_COUNT = 26;

export function KnowledgeScene() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const activeCanvas = canvas;

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0, 12.5);

    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      canvas: activeCanvas,
      powerPreference: "high-performance",
    });
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.8));

    const group = new THREE.Group();
    scene.add(group);

    const nodeGeometry = new THREE.SphereGeometry(0.055, 18, 18);
    const coreMaterial = new THREE.MeshBasicMaterial({
      color: 0x0f766e,
      transparent: true,
      opacity: 0.38,
    });
    const ghostMaterial = new THREE.MeshBasicMaterial({
      color: 0x6f7f45,
      transparent: true,
      opacity: 0.16,
    });

    const nodes: THREE.Vector3[] = [];
    for (let index = 0; index < NODE_COUNT; index += 1) {
      const angle = index * 1.71;
      const radius = 2.1 + (index % 5) * 0.46;
      const x = Math.cos(angle) * radius;
      const y = Math.sin(angle * 0.86) * (1.2 + (index % 3) * 0.22);
      const z = Math.sin(angle) * 1.2 + (index % 4) * 0.34;
      const position = new THREE.Vector3(x, y, z);
      nodes.push(position);

      const mesh = new THREE.Mesh(
        nodeGeometry,
        index % 4 === 0 ? coreMaterial : ghostMaterial,
      );
      mesh.position.copy(position);
      group.add(mesh);
    }

    const linePositions: number[] = [];
    for (let index = 0; index < nodes.length; index += 1) {
      const from = nodes[index];
      const to = nodes[(index + 3) % nodes.length];
      linePositions.push(from.x, from.y, from.z, to.x, to.y, to.z);
    }

    const lineGeometry = new THREE.BufferGeometry();
    lineGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(linePositions, 3),
    );
    const lineMaterial = new THREE.LineBasicMaterial({
      color: 0x0f766e,
      transparent: true,
      opacity: 0.12,
    });
    group.add(new THREE.LineSegments(lineGeometry, lineMaterial));

    const haloGeometry = new THREE.TorusGeometry(2.9, 0.003, 8, 160);
    const haloMaterial = new THREE.MeshBasicMaterial({
      color: 0x0f766e,
      transparent: true,
      opacity: 0.08,
    });
    const halo = new THREE.Mesh(haloGeometry, haloMaterial);
    halo.rotation.x = Math.PI / 2.45;
    group.add(halo);

    let frameId = 0;

    function resize() {
      const width = activeCanvas.clientWidth;
      const height = activeCanvas.clientHeight;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    }

    function render(time = 0) {
      const progress = time * 0.00018;
      if (!prefersReducedMotion) {
        group.rotation.y = progress;
        group.rotation.x = Math.sin(progress * 1.7) * 0.08;
        halo.rotation.z = progress * 1.8;
      }
      renderer.render(scene, camera);
      frameId = window.requestAnimationFrame(render);
    }

    resize();
    render();
    window.addEventListener("resize", resize);

    return () => {
      window.removeEventListener("resize", resize);
      window.cancelAnimationFrame(frameId);
      lineGeometry.dispose();
      lineMaterial.dispose();
      haloGeometry.dispose();
      haloMaterial.dispose();
      nodeGeometry.dispose();
      coreMaterial.dispose();
      ghostMaterial.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 h-[100dvh] w-screen opacity-70"
    />
  );
}
