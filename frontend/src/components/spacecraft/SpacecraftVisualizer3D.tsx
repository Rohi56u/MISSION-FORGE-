import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { Box, RefreshCw, ShieldCheck, Table as TableIcon, Layers, RotateCcw } from 'lucide-react';
import { ComponentSpecInput } from '../../lib/api';

export interface SpacecraftVisualizer3DProps {
  components: ComponentSpecInput[];
  selectedComponentId?: string | null;
  onSelectComponent?: (id: string | null) => void;
  dryMassKg?: number;
  wetMassKg?: number;
  powerDrawW?: number;
  powerGenW?: number;
}

const isWebGLAvailable = (): boolean => {
  if (typeof window === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    );
  } catch {
    return false;
  }
};

export const SpacecraftVisualizer3D: React.FC<SpacecraftVisualizer3DProps> = ({
  components,
  selectedComponentId,
  onSelectComponent,
  dryMassKg = 0,
  wetMassKg = 0,
  powerDrawW = 0,
  powerGenW = 0,
}) => {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [webGlSupported] = useState<boolean>(isWebGLAvailable);
  const [forceAccessibleMode, setForceAccessibleMode] = useState<boolean>(false);
  const [wireframe, setWireframe] = useState<boolean>(false);
  const [autoRotate, setAutoRotate] = useState<boolean>(true);
  const [hoveredSubsystem, setHoveredSubsystem] = useState<string | null>(null);

  // Three.js instances ref for controls
  const controlsRef = useRef<{
    resetCamera: () => void;
    zoomIn: () => void;
    zoomOut: () => void;
    rotateLeft: () => void;
    rotateRight: () => void;
  } | null>(null);

  // Group components by subsystem
  const subsystemCounts = React.useMemo(() => {
    const counts: Record<string, number> = {};
    components.forEach((c) => {
      const sub = c.subsystem || 'STRUCTURE';
      counts[sub] = (counts[sub] || 0) + 1;
    });
    return counts;
  }, [components]);

  // Selected component subsystem
  const selectedSubsystem = React.useMemo(() => {
    if (!selectedComponentId) return null;
    const comp = components.find((c) => c.id === selectedComponentId);
    return comp ? comp.subsystem : null;
  }, [components, selectedComponentId]);

  useEffect(() => {
    if (!webGlSupported || forceAccessibleMode) return;
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 640;
    const height = 400;

    // 1. Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0f1d);

    // 2. Camera setup
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(22, 14, 26);
    camera.lookAt(0, 0, 0);

    // 3. Renderer setup
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      container.appendChild(renderer.domElement);
    } catch {
      return;
    }

    // 4. Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xfff5ea, 2.0);
    dirLight1.position.set(30, 40, 20);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x38bdf8, 1.0);
    dirLight2.position.set(-20, -10, -20);
    scene.add(dirLight2);

    // 5. Grid plane (ground coordinate reference)
    const gridHelper = new THREE.GridHelper(30, 30, 0x1e293b, 0x0f172a);
    gridHelper.position.y = -6;
    scene.add(gridHelper);

    // Spacecraft root group
    const spacecraftGroup = new THREE.Group();
    scene.add(spacecraftGroup);

    // Collection of disposable resources
    const geometries: THREE.BufferGeometry[] = [];
    const materials: THREE.Material[] = [];

    // Helper to create and track materials
    const makeMaterial = (color: number, emissive: number = 0x000000, roughness: number = 0.4) => {
      const mat = new THREE.MeshStandardMaterial({
        color,
        emissive,
        roughness,
        metalness: 0.5,
        wireframe,
      });
      materials.push(mat);
      return mat;
    };

    // Subsystem Meshes map for raycasting/highlighting
    const interactiveMeshes: Array<{ mesh: THREE.Mesh; subsystem: string }> = [];

    // 6. Central Bus Chassis (STRUCTURE)
    const isStructureSelected = selectedSubsystem === 'STRUCTURE';
    const busGeom = new THREE.BoxGeometry(6, 7, 6);
    geometries.push(busGeom);
    const busMat = makeMaterial(
      0x64748b,
      isStructureSelected ? 0x0284c7 : 0x0f172a,
      0.3
    );
    const busMesh = new THREE.Mesh(busGeom, busMat);
    busMesh.userData = { subsystem: 'STRUCTURE' };
    spacecraftGroup.add(busMesh);
    interactiveMeshes.push({ mesh: busMesh, subsystem: 'STRUCTURE' });

    // Chassis gold foil MLI panels accent
    const foilGeom = new THREE.BoxGeometry(5.8, 6.8, 0.2);
    geometries.push(foilGeom);
    const foilMat = makeMaterial(0xd97706, 0x78350f, 0.2);
    const foilFront = new THREE.Mesh(foilGeom, foilMat);
    foilFront.position.z = 3.01;
    spacecraftGroup.add(foilFront);

    // 7. Solar Array Wings (POWER)
    const hasPower = (subsystemCounts['POWER'] || 0) > 0;
    const isPowerSelected = selectedSubsystem === 'POWER';
    const wingGeom = new THREE.BoxGeometry(10, 0.2, 3.6);
    geometries.push(wingGeom);
    const wingMat = makeMaterial(
      hasPower ? 0x1d4ed8 : 0x334155,
      isPowerSelected ? 0x2563eb : (hasPower ? 0x1e3a8a : 0x000000),
      0.2
    );

    // Left Wing
    const leftWing = new THREE.Mesh(wingGeom, wingMat);
    leftWing.position.set(-8.5, 0, 0);
    leftWing.userData = { subsystem: 'POWER' };
    spacecraftGroup.add(leftWing);
    interactiveMeshes.push({ mesh: leftWing, subsystem: 'POWER' });

    // Right Wing
    const rightWing = new THREE.Mesh(wingGeom, wingMat);
    rightWing.position.set(8.5, 0, 0);
    rightWing.userData = { subsystem: 'POWER' };
    spacecraftGroup.add(rightWing);
    interactiveMeshes.push({ mesh: rightWing, subsystem: 'POWER' });

    // Solar Wing Yokes / Struts
    const yokeGeom = new THREE.CylinderGeometry(0.15, 0.15, 3, 8);
    geometries.push(yokeGeom);
    const yokeMat = makeMaterial(0x94a3b8);
    const leftYoke = new THREE.Mesh(yokeGeom, yokeMat);
    leftYoke.rotation.z = Math.PI / 2;
    leftYoke.position.set(-3.5, 0, 0);
    spacecraftGroup.add(leftYoke);

    const rightYoke = new THREE.Mesh(yokeGeom, yokeMat);
    rightYoke.rotation.z = Math.PI / 2;
    rightYoke.position.set(3.5, 0, 0);
    spacecraftGroup.add(rightYoke);

    // 8. High-Gain Antenna Dish (TELECOM)
    const hasTelecom = (subsystemCounts['TELECOM'] || 0) > 0;
    const isTelecomSelected = selectedSubsystem === 'TELECOM';
    // Parabolic dish approximated via open cylinder/cone
    const dishGeom = new THREE.ConeGeometry(2.4, 1.2, 24, 1, true);
    geometries.push(dishGeom);
    const dishMat = makeMaterial(
      hasTelecom ? 0xf8fafc : 0x64748b,
      isTelecomSelected ? 0x38bdf8 : 0x000000,
      0.3
    );
    const dishMesh = new THREE.Mesh(dishGeom, dishMat);
    dishMesh.rotation.x = Math.PI; // Opening upward
    dishMesh.position.set(0, 4.4, 0);
    dishMesh.userData = { subsystem: 'TELECOM' };
    spacecraftGroup.add(dishMesh);
    interactiveMeshes.push({ mesh: dishMesh, subsystem: 'TELECOM' });

    // Antenna Feed Horn & Mast
    const mastGeom = new THREE.CylinderGeometry(0.08, 0.08, 2.2, 8);
    geometries.push(mastGeom);
    const mastMat = makeMaterial(0x94a3b8);
    const mastMesh = new THREE.Mesh(mastGeom, mastMat);
    mastMesh.position.set(0, 4.8, 0);
    spacecraftGroup.add(mastMesh);

    // 9. Propulsion Nozzles & Tank (PROPULSION)
    const hasProp = (subsystemCounts['PROPULSION'] || 0) > 0;
    const isPropSelected = selectedSubsystem === 'PROPULSION';
    const nozzleGeom = new THREE.ConeGeometry(1.2, 2.0, 16, 1, true);
    geometries.push(nozzleGeom);
    const nozzleMat = makeMaterial(
      hasProp ? 0x475569 : 0x1e293b,
      isPropSelected ? 0xf97316 : (hasProp ? 0x7c2d12 : 0x000000),
      0.6
    );
    const nozzleMesh = new THREE.Mesh(nozzleGeom, nozzleMat);
    nozzleMesh.position.set(0, -4.2, 0);
    nozzleMesh.userData = { subsystem: 'PROPULSION' };
    spacecraftGroup.add(nozzleMesh);
    interactiveMeshes.push({ mesh: nozzleMesh, subsystem: 'PROPULSION' });

    // 4 RCS Thruster Pods around shoulders
    const rcsGeom = new THREE.BoxGeometry(0.5, 0.5, 0.5);
    geometries.push(rcsGeom);
    const rcsMat = makeMaterial(0x94a3b8);
    const rcsOffsets = [
      [3.1, 2.5, 3.1],
      [-3.1, 2.5, 3.1],
      [3.1, 2.5, -3.1],
      [-3.1, 2.5, -3.1],
    ];
    rcsOffsets.forEach(([rx, ry, rz]) => {
      const rcsMesh = new THREE.Mesh(rcsGeom, rcsMat);
      rcsMesh.position.set(rx, ry, rz);
      spacecraftGroup.add(rcsMesh);
    });

    // 10. Science Instrument Turret / Optical Camera (SCIENCE)
    const hasScience = (subsystemCounts['SCIENCE'] || 0) > 0;
    const isScienceSelected = selectedSubsystem === 'SCIENCE';
    const sciGeom = new THREE.CylinderGeometry(0.8, 0.9, 1.8, 16);
    geometries.push(sciGeom);
    const sciMat = makeMaterial(
      hasScience ? 0x059669 : 0x334155,
      isScienceSelected ? 0x10b981 : (hasScience ? 0x064e3b : 0x000000),
      0.3
    );
    const sciMesh = new THREE.Mesh(sciGeom, sciMat);
    sciMesh.rotation.x = Math.PI / 2;
    sciMesh.position.set(1.8, 2.2, 3.8);
    sciMesh.userData = { subsystem: 'SCIENCE' };
    spacecraftGroup.add(sciMesh);
    interactiveMeshes.push({ mesh: sciMesh, subsystem: 'SCIENCE' });

    // Science Lens aperture
    const lensGeom = new THREE.CircleGeometry(0.65, 16);
    geometries.push(lensGeom);
    const lensMat = makeMaterial(0x06b6d4, 0x0891b2, 0.1);
    const lensMesh = new THREE.Mesh(lensGeom, lensMat);
    lensMesh.position.set(1.8, 2.2, 4.71);
    spacecraftGroup.add(lensMesh);

    // 11. ADCS Star Tracker & Reaction Wheels (ADCS)
    const hasAdcs = (subsystemCounts['ADCS'] || 0) > 0;
    const isAdcsSelected = selectedSubsystem === 'ADCS';
    const adcsGeom = new THREE.CylinderGeometry(0.5, 0.5, 0.8, 12);
    geometries.push(adcsGeom);
    const adcsMat = makeMaterial(
      hasAdcs ? 0xa855f7 : 0x334155,
      isAdcsSelected ? 0xc084fc : (hasAdcs ? 0x581c87 : 0x000000),
      0.4
    );
    const adcsMesh = new THREE.Mesh(adcsGeom, adcsMat);
    adcsMesh.position.set(-2.0, 2.4, 3.4);
    adcsMesh.rotation.x = -Math.PI / 4;
    adcsMesh.userData = { subsystem: 'ADCS' };
    spacecraftGroup.add(adcsMesh);
    interactiveMeshes.push({ mesh: adcsMesh, subsystem: 'ADCS' });

    // 12. Thermal Louvers & Radiator Panels (THERMAL)
    const hasThermal = (subsystemCounts['THERMAL'] || 0) > 0;
    const isThermalSelected = selectedSubsystem === 'THERMAL';
    const radGeom = new THREE.BoxGeometry(0.1, 5.0, 4.0);
    geometries.push(radGeom);
    const radMat = makeMaterial(
      hasThermal ? 0xe2e8f0 : 0x475569,
      isThermalSelected ? 0xffffff : 0x000000,
      0.1
    );
    const radMesh = new THREE.Mesh(radGeom, radMat);
    radMesh.position.set(3.06, 0, 0);
    radMesh.userData = { subsystem: 'THERMAL' };
    spacecraftGroup.add(radMesh);
    interactiveMeshes.push({ mesh: radMesh, subsystem: 'THERMAL' });

    // Interactive Raycaster for part selection
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onPointerDown = (e: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(
        interactiveMeshes.map((m) => m.mesh)
      );

      if (intersects.length > 0) {
        const hitSubsystem = intersects[0].object.userData.subsystem as string;
        // Find matching component in ledger
        const match = components.find((c) => c.subsystem === hitSubsystem);
        if (match && onSelectComponent) {
          onSelectComponent(match.id || null);
        }
      }
    };

    const onPointerMove = (e: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(
        interactiveMeshes.map((m) => m.mesh)
      );

      if (intersects.length > 0) {
        setHoveredSubsystem(intersects[0].object.userData.subsystem as string);
      } else {
        setHoveredSubsystem(null);
      }
    };

    renderer.domElement.addEventListener('pointerdown', onPointerDown);
    renderer.domElement.addEventListener('pointermove', onPointerMove);

    // Orbit Drag Controls
    let isDragging = false;
    let prevMouse = { x: 0, y: 0 };
    let spherical = { radius: 36, theta: 0.8, phi: 1.1 };

    const updateCameraPos = () => {
      camera.position.x = spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta);
      camera.position.y = spherical.radius * Math.cos(spherical.phi);
      camera.position.z = spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta);
      camera.lookAt(0, 0, 0);
    };
    updateCameraPos();

    const onMouseDown = (e: MouseEvent) => {
      isDragging = true;
      prevMouse = { x: e.clientX, y: e.clientY };
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      const dx = e.clientX - prevMouse.x;
      const dy = e.clientY - prevMouse.y;
      spherical.theta -= dx * 0.007;
      spherical.phi = Math.max(0.2, Math.min(Math.PI - 0.2, spherical.phi - dy * 0.007));
      updateCameraPos();
      prevMouse = { x: e.clientX, y: e.clientY };
    };

    const onMouseUp = () => {
      isDragging = false;
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      spherical.radius = Math.max(12, Math.min(80, spherical.radius + e.deltaY * 0.03));
      updateCameraPos();
    };

    const dom = renderer.domElement;
    dom.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    dom.addEventListener('wheel', onWheel, { passive: false });

    // Expose control callbacks
    controlsRef.current = {
      resetCamera: () => {
        spherical = { radius: 36, theta: 0.8, phi: 1.1 };
        updateCameraPos();
      },
      zoomIn: () => {
        spherical.radius = Math.max(12, spherical.radius - 5);
        updateCameraPos();
      },
      zoomOut: () => {
        spherical.radius = Math.min(80, spherical.radius + 5);
        updateCameraPos();
      },
      rotateLeft: () => {
        spherical.theta += 0.3;
        updateCameraPos();
      },
      rotateRight: () => {
        spherical.theta -= 0.3;
        updateCameraPos();
      },
    };

    // Resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const newWidth = entry.contentRect.width;
        if (newWidth > 0 && renderer) {
          camera.aspect = newWidth / height;
          camera.updateProjectionMatrix();
          renderer.setSize(newWidth, height);
        }
      }
    });
    resizeObserver.observe(container);

    // Animation Loop
    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      if (autoRotate && !isDragging) {
        spacecraftGroup.rotation.y += 0.004;
      }
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(animId);
      resizeObserver.disconnect();
      dom.removeEventListener('pointerdown', onPointerDown);
      dom.removeEventListener('pointermove', onPointerMove);
      dom.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      dom.removeEventListener('wheel', onWheel);

      geometries.forEach((g) => g.dispose());
      materials.forEach((m) => m.dispose());
      renderer.dispose();
      if (container.contains(dom)) {
        container.removeChild(dom);
      }
    };
  }, [webGlSupported, forceAccessibleMode, wireframe, autoRotate, components, selectedSubsystem, subsystemCounts, onSelectComponent]);

  return (
    <div className="bg-panel border border-hairline rounded-lg overflow-hidden flex flex-col shadow-panel">
      {/* Header bar */}
      <div className="px-4 py-3 border-b border-hairline flex flex-wrap items-center justify-between gap-2 bg-panel-raised">
        <div className="flex items-center space-x-2">
          <Box className="w-4 h-4 text-accent" aria-hidden="true" />
          <h2 className="text-sm font-semibold tracking-wide text-white font-mono uppercase">
            Spacecraft Subsystem Visualizer
          </h2>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-hairline">
            Procedural 3D Bus
          </span>
        </div>

        <div className="flex items-center space-x-2 text-xs">
          {/* WebGL / Table toggle */}
          <button
            onClick={() => setForceAccessibleMode(!forceAccessibleMode)}
            className={`px-2.5 py-1 rounded font-mono text-xs flex items-center space-x-1.5 border transition-all ${
              forceAccessibleMode
                ? 'bg-accent/20 border-accent text-accent'
                : 'bg-panel border-hairline text-slate-300 hover:text-white'
            }`}
            title="Toggle accessible component table view"
            aria-label="Toggle accessible tabular view"
          >
            <TableIcon className="w-3.5 h-3.5" />
            <span>{forceAccessibleMode ? '3D VIEW' : 'TABLE VIEW'}</span>
          </button>

          {!forceAccessibleMode && (
            <>
              {/* Wireframe toggle */}
              <button
                onClick={() => setWireframe(!wireframe)}
                className={`p-1.5 rounded border ${
                  wireframe
                    ? 'bg-accent/20 border-accent text-accent'
                    : 'bg-panel border-hairline text-slate-400 hover:text-white'
                }`}
                title="Toggle Wireframe"
                aria-label="Toggle Wireframe mode"
              >
                <Layers className="w-3.5 h-3.5" />
              </button>

              {/* Auto rotate toggle */}
              <button
                onClick={() => setAutoRotate(!autoRotate)}
                className={`p-1.5 rounded border ${
                  autoRotate
                    ? 'bg-panel border-accent text-accent'
                    : 'bg-panel border-hairline text-slate-400 hover:text-white'
                }`}
                title="Toggle Auto Rotation"
                aria-label="Toggle Auto Rotation"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>

              {/* Reset camera */}
              <button
                onClick={() => controlsRef.current?.resetCamera()}
                className="p-1.5 rounded bg-panel border border-hairline text-slate-400 hover:text-white"
                title="Reset Camera View"
                aria-label="Reset Camera View"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Honest Engineering Disclaimer Banner */}
      <div
        role="note"
        aria-label="Procedural visualization disclosure"
        className="px-4 py-2 bg-slate-900/90 border-b border-hairline/60 text-[11px] font-mono text-slate-400 flex items-center justify-between"
      >
        <div className="flex items-center space-x-2">
          <ShieldCheck className="w-3.5 h-3.5 text-accent flex-shrink-0" />
          <span>
            SCHEMATIC SUBSYSTEM VIEW: Procedural layout represents subsystem architecture & budgets. Non-flight geometric CAD.
          </span>
        </div>
        {hoveredSubsystem && (
          <span className="text-white font-semibold uppercase bg-slate-800 px-2 py-0.5 rounded border border-hairline text-[10px]">
            HOVER: {hoveredSubsystem}
          </span>
        )}
      </div>

      {/* Viewport or Accessible Table View */}
      {forceAccessibleMode || !webGlSupported ? (
        <div className="p-4 bg-canvas min-h-[360px] overflow-x-auto" data-testid="accessible-component-table">
          <div className="text-xs text-slate-400 mb-3 flex items-center justify-between">
            <span className="font-semibold text-white">Configured Flight Subsystem Components Ledger</span>
            <span className="font-mono text-[11px]">Total Active: {components.length} components</span>
          </div>
          {components.length === 0 ? (
            <div className="py-12 text-center text-slate-500 font-mono text-xs">
              NO COMPONENTS CURRENTLY ASSIGNED TO SPACECRAFT CONFIGURATION.
            </div>
          ) : (
            <table className="w-full text-left text-xs font-mono border-collapse" aria-label="Component specifications table">
              <thead>
                <tr className="border-b border-hairline text-slate-400 uppercase text-[10px]">
                  <th className="py-2 px-3">Subsystem</th>
                  <th className="py-2 px-3">Component Name</th>
                  <th className="py-2 px-3 text-right">Mass (kg)</th>
                  <th className="py-2 px-3 text-right">Power Draw (W)</th>
                  <th className="py-2 px-3 text-right">Power Gen (W)</th>
                  <th className="py-2 px-3 text-right">Cost (USD)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline/40">
                {components.map((c, idx) => (
                  <tr
                    key={c.id || idx}
                    onClick={() => onSelectComponent && onSelectComponent(c.id || null)}
                    className={`cursor-pointer transition-colors ${
                      c.id === selectedComponentId ? 'bg-accent/15 text-white font-semibold' : 'text-slate-300 hover:bg-panel-raised/50'
                    }`}
                  >
                    <td className="py-2 px-3">
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 border border-hairline text-[10px] text-slate-300">
                        {c.subsystem}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-white">{c.name}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{c.mass_kg.toFixed(2)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{c.power_draw_w.toFixed(1)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{c.power_generation_w.toFixed(1)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">${c.cost_usd.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="relative w-full h-[400px] bg-canvas" ref={mountRef} data-testid="spacecraft-3d-canvas">
          {/* Floating On-Canvas Subsystem Breakdown HUD */}
          <div className="absolute top-3 left-3 bg-panel/90 backdrop-blur-sm border border-hairline p-2.5 rounded text-[11px] font-mono pointer-events-none space-y-1">
            <div className="text-slate-400 font-semibold mb-1">CONFIGURATION TOTALS</div>
            <div className="text-slate-300">Dry Mass: <span className="text-white font-semibold tabular-nums">{dryMassKg.toFixed(1)} kg</span></div>
            <div className="text-slate-300">Wet Mass: <span className="text-white font-semibold tabular-nums">{wetMassKg.toFixed(1)} kg</span></div>
            <div className="text-slate-300">Power Draw: <span className="text-white font-semibold tabular-nums">{powerDrawW.toFixed(1)} W</span></div>
            <div className="text-slate-300">Power Gen: <span className="text-emerald-400 font-semibold tabular-nums">{powerGenW.toFixed(1)} W</span></div>
          </div>

          {/* Canvas Navigation Helper */}
          <div className="absolute bottom-3 right-3 text-[10px] font-mono text-slate-500 bg-panel/80 px-2 py-1 rounded border border-hairline/60 pointer-events-none">
            DRAG TO ROTATE • SCROLL TO ZOOM • CLICK TO SELECT
          </div>
        </div>
      )}
    </div>
  );
};
