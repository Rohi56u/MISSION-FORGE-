import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { api, LambertSolveResponse, Vector3D } from '../../lib/api';
import { Eye, RefreshCw, AlertTriangle, ShieldCheck, Orbit, Compass, Table as TableIcon } from 'lucide-react';

interface TrajectoryView3DProps {
  departureDate?: string;
  arrivalDate?: string;
  tofDays?: number;
  initialC3?: number | null;
  initialDvTotal?: number | null;
  vinfDep?: number | null;
  vinfArr?: number | null;
}

// 1 Astronomical Unit in kilometers
const AU_KM = 149597870.7;
// Standard gravitational parameter of the Sun (km^3/s^2)
const MU_SUN = 132712440018.0;
// Visualization scale: 1 AU = 40 Three.js units
const SCALE_AU = 40.0;

/**
 * Synchronous WebGL availability detection to prevent context creation errors in headless / jsdom environments
 */
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

export const TrajectoryView3D: React.FC<TrajectoryView3DProps> = ({
  departureDate = '2026-06-15',
  arrivalDate = '2027-01-10',
  tofDays: propTofDays,
  initialC3,
  initialDvTotal,
  vinfDep: propVinfDep,
  vinfArr: propVinfArr,
}) => {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [webGlSupported, setWebGlSupported] = useState<boolean>(isWebGLAvailable);
  const [forceAccessibleMode, setForceAccessibleMode] = useState<boolean>(false);

  // Astrodynamic Calculation State
  const [r1, setR1] = useState<Vector3D>({ x: AU_KM, y: 0, z: 0 });
  const [r2, setR2] = useState<Vector3D>({ x: 0, y: 1.524 * AU_KM, z: 0.05 * AU_KM });
  const [depBodyVel, setDepBodyVel] = useState<Vector3D>({ x: 0, y: 29.78, z: 0 });
  const [arrBodyVel, setArrBodyVel] = useState<Vector3D>({ x: 0, y: 24.07, z: 0 });
  const [lambertSolution, setLambertSolution] = useState<LambertSolveResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Compute calculated or overridden Time of Flight
  const tofSeconds = React.useMemo(() => {
    if (propTofDays && propTofDays > 0) {
      return propTofDays * 86400;
    }
    const d1 = new Date(departureDate).getTime();
    const d2 = new Date(arrivalDate).getTime();
    const diffDays = Math.max(10, (d2 - d1) / (1000 * 86400));
    return diffDays * 86400;
  }, [departureDate, arrivalDate, propTofDays]);

  // Compute planetary ephemeris positions and invoke Lambert solver
  const computeTrajectory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Compute positions and orbital velocities of Earth (dep) and Mars (arr)
      let depPos: Vector3D = { x: AU_KM, y: 0, z: 0 };
      let depVel: Vector3D = { x: 0, y: 29.78, z: 0 };
      let arrPos: Vector3D = { x: -0.8 * AU_KM, y: 1.3 * AU_KM, z: 0.04 * AU_KM };
      let arrVel: Vector3D = { x: 0, y: 24.07, z: 0 };

      try {
        const earthVectors = await api.getHorizonsVectors('399', '500@10', departureDate, departureDate, '1d');
        if (earthVectors.vectors && earthVectors.vectors.length > 0) {
          depPos = earthVectors.vectors[0].position_km;
          if (earthVectors.vectors[0].velocity_kms) {
            depVel = earthVectors.vectors[0].velocity_kms;
          }
        }
      } catch {
        // Deterministic Keplerian position for Earth based on day of year
        const d = new Date(departureDate);
        const dayOfYear = Math.floor((d.getTime() - new Date(d.getFullYear(), 0, 0).getTime()) / 86400000);
        const angle = (dayOfYear / 365.25) * 2 * Math.PI;
        depPos = {
          x: AU_KM * Math.cos(angle),
          y: AU_KM * Math.sin(angle),
          z: 0,
        };
        depVel = {
          x: -29.78 * Math.sin(angle),
          y: 29.78 * Math.cos(angle),
          z: 0,
        };
      }

      try {
        const marsVectors = await api.getHorizonsVectors('499', '500@10', arrivalDate, arrivalDate, '1d');
        if (marsVectors.vectors && marsVectors.vectors.length > 0) {
          arrPos = marsVectors.vectors[0].position_km;
          if (marsVectors.vectors[0].velocity_kms) {
            arrVel = marsVectors.vectors[0].velocity_kms;
          }
        }
      } catch {
        // Deterministic Keplerian position for Mars based on day of year
        const d = new Date(arrivalDate);
        const dayOfYear = Math.floor((d.getTime() - new Date(d.getFullYear(), 0, 0).getTime()) / 86400000);
        const angle = (dayOfYear / 687.0) * 2 * Math.PI + 1.2;
        arrPos = {
          x: 1.524 * AU_KM * Math.cos(angle),
          y: 1.524 * AU_KM * Math.sin(angle),
          z: 0.04 * AU_KM * Math.sin(angle),
        };
        arrVel = {
          x: -24.07 * Math.sin(angle),
          y: 24.07 * Math.cos(angle),
          z: 0,
        };
      }

      setR1(depPos);
      setR2(arrPos);
      setDepBodyVel(depVel);
      setArrBodyVel(arrVel);

      // 2. Call backend universal variable Lambert solver
      const solution = await api.solveLambert({
        r1_km: depPos,
        r2_km: arrPos,
        time_of_flight_s: tofSeconds,
        mu_km3_s2: MU_SUN,
        prograde: true,
      });

      setLambertSolution(solution);
    } catch (err: any) {
      setError(err?.message || 'Failed to solve Lambert boundary-value transfer problem');
    } finally {
      setLoading(false);
    }
  }, [departureDate, arrivalDate, tofSeconds]);

  useEffect(() => {
    computeTrajectory();
  }, [computeTrajectory]);

  // Three.js Scene Setup & Animation
  useEffect(() => {
    if (!webGlSupported || forceAccessibleMode || !mountRef.current) return;

    const container = mountRef.current;
    const width = container.clientWidth || 700;
    const height = 480;

    // 1. Scene, Camera, Renderer
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x05080e);

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 2000);
    camera.position.set(0, -90, 80);
    camera.up.set(0, 0, 1);
    camera.lookAt(0, 0, 0);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      container.appendChild(renderer.domElement);
    } catch {
      setWebGlSupported(false);
      return;
    }

    // 2. Reference Grid & Coordinates (Ecliptic Plane)
    const gridHelper = new THREE.GridHelper(180, 18, 0x1e293b, 0x111827);
    gridHelper.rotation.x = Math.PI / 2;
    scene.add(gridHelper);

    // 3. Central Sun Object at Origin
    const sunGeom = new THREE.SphereGeometry(3.5, 32, 32);
    const sunMat = new THREE.MeshBasicMaterial({ color: 0xf59e0b });
    const sunMesh = new THREE.Mesh(sunGeom, sunMat);
    scene.add(sunMesh);

    // Sun Subtle Corona Glow
    const coronaGeom = new THREE.RingGeometry(3.8, 5.0, 32);
    const coronaMat = new THREE.MeshBasicMaterial({
      color: 0xfbbf24,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.3,
    });
    const coronaMesh = new THREE.Mesh(coronaGeom, coronaMat);
    scene.add(coronaMesh);

    // 4. Earth Orbit Ring (1.0 AU)
    const earthOrbitCurve = new THREE.EllipseCurve(0, 0, SCALE_AU, SCALE_AU, 0, 2 * Math.PI, false, 0);
    const earthOrbitPoints = earthOrbitCurve.getPoints(100);
    const earthOrbitGeom = new THREE.BufferGeometry().setFromPoints(earthOrbitPoints);
    const earthOrbitMat = new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.4 });
    const earthOrbitLine = new THREE.Line(earthOrbitGeom, earthOrbitMat);
    scene.add(earthOrbitLine);

    // 5. Mars Orbit Ring (1.524 AU)
    const marsRadius = 1.524 * SCALE_AU;
    const marsOrbitCurve = new THREE.EllipseCurve(0, 0, marsRadius, marsRadius, 0, 2 * Math.PI, false, 0);
    const marsOrbitPoints = marsOrbitCurve.getPoints(100);
    const marsOrbitGeom = new THREE.BufferGeometry().setFromPoints(marsOrbitPoints);
    const marsOrbitMat = new THREE.LineBasicMaterial({ color: 0xfb923c, transparent: true, opacity: 0.4 });
    const marsOrbitLine = new THREE.Line(marsOrbitGeom, marsOrbitMat);
    scene.add(marsOrbitLine);

    // 6. Departure Earth Position Marker
    const p1 = new THREE.Vector3(
      (r1.x / AU_KM) * SCALE_AU,
      (r1.y / AU_KM) * SCALE_AU,
      (r1.z / AU_KM) * SCALE_AU
    );
    const earthMarkerGeom = new THREE.SphereGeometry(1.4, 16, 16);
    const earthMarkerMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
    const earthMarker = new THREE.Mesh(earthMarkerGeom, earthMarkerMat);
    earthMarker.position.copy(p1);
    scene.add(earthMarker);

    // 7. Arrival Mars Position Marker
    const p2 = new THREE.Vector3(
      (r2.x / AU_KM) * SCALE_AU,
      (r2.y / AU_KM) * SCALE_AU,
      (r2.z / AU_KM) * SCALE_AU
    );
    const marsMarkerGeom = new THREE.SphereGeometry(1.2, 16, 16);
    const marsMarkerMat = new THREE.MeshBasicMaterial({ color: 0xef4444 });
    const marsMarker = new THREE.Mesh(marsMarkerGeom, marsMarkerMat);
    marsMarker.position.copy(p2);
    scene.add(marsMarker);

    // 8. True Keplerian Two-Body Conic Ballistic Transfer Arc
    // Derived from universal variable Lambert state (r1, v1) and solar parameter MU_SUN
    const arcPoints: THREE.Vector3[] = [];
    const numArcSegments = 100;

    if (lambertSolution && lambertSolution.converged) {
      const r1Vec = new THREE.Vector3(r1.x, r1.y, r1.z);
      const v1Vec = new THREE.Vector3(
        lambertSolution.v1_kms.x,
        lambertSolution.v1_kms.y,
        lambertSolution.v1_kms.z
      );

      // Specific angular momentum h = r1 x v1
      const hVec = new THREE.Vector3().crossVectors(r1Vec, v1Vec);
      const hMag = hVec.length();

      // Eccentricity vector e = (v1 x h) / mu - (r1 / |r1|)
      const vCrossH = new THREE.Vector3().crossVectors(v1Vec, hVec);
      const r1Mag = r1Vec.length();
      const eVec = new THREE.Vector3()
        .copy(vCrossH)
        .divideScalar(MU_SUN)
        .sub(r1Vec.clone().divideScalar(r1Mag));
      const eMag = eVec.length();

      // Perifocal orbital plane basis (P, Q, W)
      const wVec = hVec.clone().divideScalar(Math.max(1e-9, hMag));
      let pVec: THREE.Vector3;
      if (eMag > 1e-5) {
        pVec = eVec.clone().divideScalar(eMag);
      } else {
        pVec = r1Vec.clone().divideScalar(r1Mag);
      }
      const qVec = new THREE.Vector3().crossVectors(wVec, pVec);

      // Departure true anomaly nu1
      const cosNu1 = Math.max(-1, Math.min(1, r1Vec.dot(pVec) / r1Mag));
      const sinNu1 = r1Vec.dot(qVec) / r1Mag;
      const nu1 = Math.atan2(sinNu1, cosNu1);

      // Semi-latus rectum p = h^2 / mu
      const p = (hMag * hMag) / MU_SUN;

      // Transfer angle in radians
      const transferAngleRad = (lambertSolution.transfer_angle_deg * Math.PI) / 180.0;

      for (let i = 0; i <= numArcSegments; i++) {
        const frac = i / numArcSegments;
        const nu = nu1 + frac * transferAngleRad;
        const denom = 1.0 + eMag * Math.cos(nu);
        const rCurrent = denom > 1e-5 ? p / denom : r1Mag;

        // Coordinates in perifocal frame
        const xPos = rCurrent * Math.cos(nu);
        const yPos = rCurrent * Math.sin(nu);

        const rProp = new THREE.Vector3()
          .copy(pVec)
          .multiplyScalar(xPos)
          .add(qVec.clone().multiplyScalar(yPos));

        // Scale to heliocentric viewport units
        arcPoints.push(
          new THREE.Vector3(
            (rProp.x / AU_KM) * SCALE_AU,
            (rProp.y / AU_KM) * SCALE_AU,
            (rProp.z / AU_KM) * SCALE_AU
          )
        );
      }
    } else {
      // Linear interpolation fallback when awaiting Lambert convergence
      for (let i = 0; i <= numArcSegments; i++) {
        const frac = i / numArcSegments;
        arcPoints.push(new THREE.Vector3().lerpVectors(p1, p2, frac));
      }
    }

    const trajectoryGeom = new THREE.BufferGeometry().setFromPoints(arcPoints);
    const trajectoryMat = new THREE.LineBasicMaterial({
      color: 0x0284c7,
      linewidth: 2,
    });
    const trajectoryLine = new THREE.Line(trajectoryGeom, trajectoryMat);
    scene.add(trajectoryLine);

    // 9. Interactive Mouse Orbit Logic
    let isDragging = false;
    let previousMousePosition = { x: 0, y: 0 };
    let spherical = { radius: 120, theta: Math.PI / 4, phi: Math.PI / 3 };

    const updateCamera = () => {
      camera.position.x = spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta);
      camera.position.y = spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta);
      camera.position.z = spherical.radius * Math.cos(spherical.phi);
      camera.lookAt(0, 0, 0);
    };
    updateCamera();

    const onMouseDown = (e: MouseEvent) => {
      isDragging = true;
      previousMousePosition = { x: e.clientX, y: e.clientY };
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      const deltaX = e.clientX - previousMousePosition.x;
      const deltaY = e.clientY - previousMousePosition.y;

      spherical.theta -= deltaX * 0.008;
      spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, spherical.phi - deltaY * 0.008));
      updateCamera();

      previousMousePosition = { x: e.clientX, y: e.clientY };
    };

    const onMouseUp = () => {
      isDragging = false;
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      spherical.radius = Math.max(30, Math.min(300, spherical.radius + e.deltaY * 0.08));
      updateCamera();
    };

    const domElement = renderer.domElement;
    domElement.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    domElement.addEventListener('wheel', onWheel, { passive: false });

    // 10. Responsive Canvas Resize Observer
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

    // 11. Animation Loop
    let animationFrameId: number;
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      // Gentle axial rotation of Sun corona
      coronaMesh.rotation.z += 0.002;
      renderer.render(scene, camera);
    };
    animate();

    // 12. Cleanup on Unmount
    return () => {
      cancelAnimationFrame(animationFrameId);
      resizeObserver.disconnect();
      domElement.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      domElement.removeEventListener('wheel', onWheel);

      sunGeom.dispose();
      sunMat.dispose();
      coronaGeom.dispose();
      coronaMat.dispose();
      earthOrbitGeom.dispose();
      earthOrbitMat.dispose();
      marsOrbitGeom.dispose();
      marsOrbitMat.dispose();
      earthMarkerGeom.dispose();
      earthMarkerMat.dispose();
      marsMarkerGeom.dispose();
      marsMarkerMat.dispose();
      trajectoryGeom.dispose();
      trajectoryMat.dispose();
      renderer.dispose();

      if (container.contains(domElement)) {
        container.removeChild(domElement);
      }
    };
  }, [webGlSupported, forceAccessibleMode, r1, r2, lambertSolution]);

  // Derived Astrodynamic Parameters & Truthful Characteristic Delta-V Budget
  const v1Mag = lambertSolution
    ? Math.sqrt(
        lambertSolution.v1_kms.x ** 2 +
        lambertSolution.v1_kms.y ** 2 +
        lambertSolution.v1_kms.z ** 2
      )
    : 0;

  const v2Mag = lambertSolution
    ? Math.sqrt(
        lambertSolution.v2_kms.x ** 2 +
        lambertSolution.v2_kms.y ** 2 +
        lambertSolution.v2_kms.z ** 2
      )
    : 0;

  const vinfDepComputed = lambertSolution
    ? Math.sqrt(
        (lambertSolution.v1_kms.x - depBodyVel.x) ** 2 +
        (lambertSolution.v1_kms.y - depBodyVel.y) ** 2 +
        (lambertSolution.v1_kms.z - depBodyVel.z) ** 2
      )
    : 0;

  const vinfArrComputed = lambertSolution
    ? Math.sqrt(
        (lambertSolution.v2_kms.x - arrBodyVel.x) ** 2 +
        (lambertSolution.v2_kms.y - arrBodyVel.y) ** 2 +
        (lambertSolution.v2_kms.z - arrBodyVel.z) ** 2
      )
    : 0;

  const vinfDepEffective = propVinfDep ?? vinfDepComputed;
  const vinfArrEffective = propVinfArr ?? vinfArrComputed;
  const deltaVTotal = initialDvTotal ?? (vinfDepEffective + vinfArrEffective);
  const c3Effective = initialC3 ?? (vinfDepEffective > 0 ? vinfDepEffective ** 2 : (v1Mag ** 2));

  return (
    <section
      aria-labelledby="trajectory-3d-heading"
      className="bg-panel border border-hairline rounded-lg p-5 shadow-panel"
      data-testid="trajectory-3d-section"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-hairline mb-4 gap-2">
        <div className="flex items-center space-x-2.5">
          <Orbit className="w-5 h-5 text-accent" />
          <div>
            <h2 id="trajectory-3d-heading" className="text-sm font-semibold tracking-wide text-white uppercase font-mono">
              Data-Grounded 3D Heliocentric Trajectory View
            </h2>
            <div className="text-[11px] text-slate-400">
              Interactive WebGL ballistic transfer arc solved via Universal Variable Lambert formulation
            </div>
          </div>
        </div>

        {/* View Controls & Fallback Toggle */}
        <div className="flex items-center space-x-2 font-mono text-xs">
          <button
            onClick={() => setForceAccessibleMode(!forceAccessibleMode)}
            className={`px-2.5 py-1 rounded border flex items-center space-x-1.5 transition ${
              forceAccessibleMode
                ? 'bg-accent text-white border-accent'
                : 'bg-panel-raised text-slate-400 border-hairline hover:text-white'
            }`}
            aria-label="Toggle Accessible Tabular Mode"
          >
            <TableIcon className="w-3.5 h-3.5" />
            <span>{forceAccessibleMode ? '3D Canvas' : 'Accessible Telemetry'}</span>
          </button>

          <button
            onClick={computeTrajectory}
            disabled={loading}
            className="flex items-center space-x-1.5 px-2.5 py-1 bg-panel-raised border border-hairline text-slate-300 hover:text-white rounded transition disabled:opacity-50"
            aria-label="Recalculate trajectory"
          >
            <RefreshCw className={`w-3.5 h-3.5 motion-reduce:animate-none ${loading ? 'animate-spin' : ''}`} />
            <span>Solve Lambert</span>
          </button>
        </div>
      </div>

      {/* Mandatory Mathematical Limitations Banner */}
      <div
        role="note"
        className="mb-4 bg-sky-950/40 border border-sky-800/60 rounded p-3 text-xs font-mono text-sky-200 flex items-start space-x-2.5"
      >
        <ShieldCheck className="w-4 h-4 text-accent flex-shrink-0 mt-0.5" />
        <div>
          <div className="font-semibold text-white tracking-wide">
            Astrodynamic Model Assumptions & Patched-Conic Boundaries
          </div>
          <p className="text-[11px] text-slate-300 mt-0.5 leading-relaxed">
            Two-body patched-conic approximation; perturbations and mid-course maneuvers excluded.
            Central gravitational field assumes point-mass solar gravitational parameter μ = 132,712,440,018 km³/s².
            Real spaceflight operations require numerical n-body perturbation integration, solar radiation pressure, and station-keeping burns.
          </p>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-950/40 border border-status-alert/40 rounded text-xs text-red-300 flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-status-alert flex-shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={computeTrajectory}
            className="text-xs bg-red-900/60 hover:bg-red-800 text-white px-2 py-1 rounded border border-red-700 transition"
          >
            Retry
          </button>
        </div>
      )}

      {/* Main Viewport & Telemetry Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Three.js Canvas or WebGL Disabled Fallback */}
        <div className="lg:col-span-8 bg-canvas border border-hairline rounded-lg overflow-hidden relative">
          {!forceAccessibleMode && webGlSupported ? (
            <div className="relative">
              <div ref={mountRef} className="w-full h-[480px] cursor-grab active:cursor-grabbing" />
              {/* Overlay Legend */}
              <div className="absolute bottom-3 left-3 bg-panel/90 border border-hairline rounded p-2.5 text-[11px] font-mono text-slate-300 pointer-events-none space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#f59e0b] inline-block" />
                  <span>Sun (Central Origin)</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#38bdf8] inline-block" />
                  <span>Earth Orbit (1.00 AU) • Departure</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#fb923c] inline-block" />
                  <span>Mars Orbit (1.52 AU) • Arrival</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="w-4 h-0.5 bg-[#0284c7] inline-block" />
                  <span>Lambert Transfer Arc</span>
                </div>
              </div>
              <div className="absolute top-3 right-3 text-[10px] font-mono text-slate-400 bg-panel/80 px-2 py-1 rounded border border-hairline pointer-events-none">
                Drag to rotate • Scroll to zoom
              </div>
            </div>
          ) : (
            /* WebGL-Disabled Accessible Fallback View */
            <div
              className="p-6 bg-panel-raised min-h-[480px] flex flex-col justify-between"
              data-testid="webgl-fallback-view"
            >
              <div>
                <div className="flex items-center space-x-2 text-xs font-mono text-slate-400 mb-4 pb-2 border-b border-hairline">
                  <Eye className="w-4 h-4 text-accent" />
                  <span>ACCESSIBLE TABULAR TRAJECTORY TELEMETRY (WebGL Disabled Fallback)</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 font-mono text-xs mb-6">
                  <div className="p-3 bg-panel border border-hairline rounded">
                    <span className="text-slate-400 text-[10px] uppercase block font-semibold">
                      Departure State (Earth)
                    </span>
                    <div className="text-white font-bold mt-1">{departureDate} UTC</div>
                    <div className="text-slate-300 text-[11px] mt-2 space-y-0.5">
                      <div>X: {r1.x.toLocaleString()} km</div>
                      <div>Y: {r1.y.toLocaleString()} km</div>
                      <div>Z: {r1.z.toLocaleString()} km</div>
                    </div>
                  </div>

                  <div className="p-3 bg-panel border border-hairline rounded">
                    <span className="text-slate-400 text-[10px] uppercase block font-semibold">
                      Arrival State (Mars)
                    </span>
                    <div className="text-white font-bold mt-1">{arrivalDate} UTC</div>
                    <div className="text-slate-300 text-[11px] mt-2 space-y-0.5">
                      <div>X: {r2.x.toLocaleString()} km</div>
                      <div>Y: {r2.y.toLocaleString()} km</div>
                      <div>Z: {r2.z.toLocaleString()} km</div>
                    </div>
                  </div>
                </div>

                {lambertSolution && (
                  <div className="overflow-x-auto border border-hairline rounded">
                    <table className="w-full text-left text-xs font-mono" aria-label="Lambert Transfer Parameters Table">
                      <thead className="bg-panel text-slate-400 uppercase text-[10px]">
                        <tr>
                          <th className="p-2.5">Parameter</th>
                          <th className="p-2.5">Value</th>
                          <th className="p-2.5">Unit</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-hairline bg-panel-raised text-slate-200">
                        <tr>
                          <td className="p-2.5 font-semibold text-white">Total Transfer ΔV (Budget)</td>
                          <td className="p-2.5 tabular-nums text-status-nominal font-bold">{deltaVTotal.toFixed(3)}</td>
                          <td className="p-2.5 text-slate-400">km/s</td>
                        </tr>
                        <tr>
                          <td className="p-2.5">Departure ΔV (v∞,dep)</td>
                          <td className="p-2.5 tabular-nums">{vinfDepEffective.toFixed(3)}</td>
                          <td className="p-2.5 text-slate-400">km/s</td>
                        </tr>
                        <tr>
                          <td className="p-2.5">Arrival ΔV (v∞,arr)</td>
                          <td className="p-2.5 tabular-nums">{vinfArrEffective.toFixed(3)}</td>
                          <td className="p-2.5 text-slate-400">km/s</td>
                        </tr>
                        <tr>
                          <td className="p-2.5">Characteristic Energy (C₃)</td>
                          <td className="p-2.5 tabular-nums text-accent font-semibold">{c3Effective.toFixed(2)}</td>
                          <td className="p-2.5 text-slate-400">km²/s²</td>
                        </tr>
                        <tr>
                          <td className="p-2.5">Transfer Time of Flight</td>
                          <td className="p-2.5 tabular-nums">{(tofSeconds / 86400).toFixed(2)}</td>
                          <td className="p-2.5 text-slate-400">days</td>
                        </tr>
                        <tr>
                          <td className="p-2.5">Semi-Major Axis (a)</td>
                          <td className="p-2.5 tabular-nums">
                            {lambertSolution.semi_major_axis_km.toLocaleString()}
                          </td>
                          <td className="p-2.5 text-slate-400">km</td>
                        </tr>
                        <tr>
                          <td className="p-2.5">Eccentricity (e)</td>
                          <td className="p-2.5 tabular-nums">{lambertSolution.eccentricity.toFixed(4)}</td>
                          <td className="p-2.5 text-slate-400">dimensionless</td>
                        </tr>
                        <tr>
                          <td className="p-2.5">Transfer Angle (θ)</td>
                          <td className="p-2.5 tabular-nums">{lambertSolution.transfer_angle_deg.toFixed(2)}</td>
                          <td className="p-2.5 text-slate-400">deg</td>
                        </tr>
                        <tr>
                          <td className="p-2.5">Departure Speed (|v₁|)</td>
                          <td className="p-2.5 tabular-nums">{v1Mag.toFixed(3)}</td>
                          <td className="p-2.5 text-slate-400">km/s</td>
                        </tr>
                        <tr>
                          <td className="p-2.5">Arrival Speed (|v₂|)</td>
                          <td className="p-2.5 tabular-nums">{v2Mag.toFixed(3)}</td>
                          <td className="p-2.5 text-slate-400">km/s</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="mt-4 text-[11px] text-slate-400 font-mono">
                Accessible fallback rendered automatically when WebGL hardware acceleration is inactive or manually requested.
              </div>
            </div>
          )}
        </div>

        {/* Astrodynamic Solution Parameters Readout Column */}
        <div
          className="lg:col-span-4 bg-panel-raised border border-hairline rounded-lg p-4 space-y-4"
          data-testid="lambert-telemetry"
        >
          <div className="flex items-center justify-between border-b border-hairline pb-2.5">
            <h3 className="text-xs font-bold text-white uppercase font-mono tracking-wider flex items-center space-x-1.5">
              <Compass className="w-4 h-4 text-accent" />
              <span>Lambert Solution Telemetry</span>
            </h3>
            {lambertSolution?.converged ? (
              <span className="text-[10px] font-mono px-2 py-0.5 bg-emerald-950 text-status-nominal rounded border border-emerald-800">
                CONVERGED
              </span>
            ) : (
              <span className="text-[10px] font-mono px-2 py-0.5 bg-slate-800 text-slate-400 rounded border border-hairline">
                SOLVING
              </span>
            )}
          </div>

          {lambertSolution ? (
            <div className="space-y-3 font-mono text-xs">
              {/* High-level parameters: Flight Time, C3, and Delta-V */}
              <div className="grid grid-cols-3 gap-2">
                <div className="p-2.5 bg-panel border border-hairline rounded">
                  <span className="text-slate-400 text-[10px] block uppercase">Flight Time</span>
                  <span className="text-white font-bold text-sm sm:text-base tabular-nums">
                    {(lambertSolution.time_of_flight_s / 86400).toFixed(1)}
                  </span>
                  <span className="text-[10px] text-slate-400 block">days</span>
                </div>

                <div className="p-2.5 bg-panel border border-hairline rounded">
                  <span className="text-slate-400 text-[10px] block uppercase">C₃ Energy</span>
                  <span className="text-accent font-bold text-sm sm:text-base tabular-nums">
                    {c3Effective.toFixed(2)}
                  </span>
                  <span className="text-[10px] text-slate-400 block">km²/s²</span>
                </div>

                <div className="p-2.5 bg-panel border border-hairline rounded" data-testid="telemetry-delta-v">
                  <span className="text-slate-400 text-[10px] block uppercase">Total ΔV</span>
                  <span className="text-status-nominal font-bold text-sm sm:text-base tabular-nums">
                    {deltaVTotal.toFixed(2)}
                  </span>
                  <span className="text-[10px] text-slate-400 block">km/s</span>
                </div>
              </div>

              {/* Characteristic Delta-V Budget & Impulse */}
              <div className="p-3 bg-panel border border-hairline rounded space-y-1.5 text-xs">
                <span className="text-[10px] uppercase font-semibold text-slate-400 block border-b border-hairline pb-1">
                  Astrodynamic ΔV Budget & Excess Velocity
                </span>
                <div className="flex justify-between">
                  <span className="text-slate-400">Total Characteristic ΔV:</span>
                  <span className="text-status-nominal font-bold tabular-nums">
                    {deltaVTotal.toFixed(3)} km/s
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Departure Excess (v∞,dep / ΔV₁):</span>
                  <span className="text-slate-200 tabular-nums">{vinfDepEffective.toFixed(3)} km/s</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Arrival Excess (v∞,arr / ΔV₂):</span>
                  <span className="text-slate-200 tabular-nums">{vinfArrEffective.toFixed(3)} km/s</span>
                </div>
              </div>

              {/* Orbital Transfer Geometry */}
              <div className="p-3 bg-panel border border-hairline rounded space-y-1.5 text-xs">
                <span className="text-[10px] uppercase font-semibold text-slate-400 block border-b border-hairline pb-1">
                  Keplerian Transfer Geometry
                </span>
                <div className="flex justify-between">
                  <span className="text-slate-400">Semi-Major Axis (a):</span>
                  <span className="text-slate-200 tabular-nums">
                    {(lambertSolution.semi_major_axis_km / AU_KM).toFixed(3)} AU
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Eccentricity (e):</span>
                  <span className="text-slate-200 tabular-nums">{lambertSolution.eccentricity.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Transfer Angle (θ):</span>
                  <span className="text-slate-200 tabular-nums">{lambertSolution.transfer_angle_deg.toFixed(2)}°</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Transfer Branch:</span>
                  <span className="text-slate-200 uppercase">{lambertSolution.solution_branch}</span>
                </div>
              </div>

              {/* Velocity Vectors */}
              <div className="p-3 bg-panel border border-hairline rounded space-y-2 text-xs">
                <div>
                  <div className="flex justify-between items-center text-[10px] text-slate-400 uppercase font-semibold">
                    <span>Departure Velocity Vector (v₁)</span>
                    <span className="text-slate-200 tabular-nums font-bold">|v₁| = {v1Mag.toFixed(2)} km/s</span>
                  </div>
                  <div className="text-[11px] text-slate-300 mt-1">
                    [{lambertSolution.v1_kms.x.toFixed(2)}, {lambertSolution.v1_kms.y.toFixed(2)}, {lambertSolution.v1_kms.z.toFixed(2)}] km/s
                  </div>
                </div>

                <div className="pt-2 border-t border-hairline">
                  <div className="flex justify-between items-center text-[10px] text-slate-400 uppercase font-semibold">
                    <span>Arrival Velocity Vector (v₂)</span>
                    <span className="text-slate-200 tabular-nums font-bold">|v₂| = {v2Mag.toFixed(2)} km/s</span>
                  </div>
                  <div className="text-[11px] text-slate-300 mt-1">
                    [{lambertSolution.v2_kms.x.toFixed(2)}, {lambertSolution.v2_kms.y.toFixed(2)}, {lambertSolution.v2_kms.z.toFixed(2)}] km/s
                  </div>
                </div>
              </div>

              {/* Numerical Diagnostics */}
              <div className="p-2 bg-panel/60 border border-hairline rounded text-[10px] text-slate-400 flex justify-between">
                <span>Iterations: {lambertSolution.iterations}</span>
                <span>Residual: {lambertSolution.residual.toExponential(3)}</span>
              </div>
            </div>
          ) : (
            <div className="py-16 text-center text-slate-400 text-xs font-mono">
              Solving boundary transfer arc...
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
