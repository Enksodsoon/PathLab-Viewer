import { m, useReducedMotion } from 'motion/react'

const PATH_COUNT = 24

function makePaths(position: number) {
  return Array.from({ length: PATH_COUNT }, (_, index) => {
    const inset = index * 5 * position
    const rise = index * 6
    return {
      d: `M${-380 + inset} ${-189 - rise}C${-380 + inset} ${-189 - rise} ${-312 + inset} ${216 - rise} ${152 + inset} ${343 - rise}C${616 + inset} ${470 - rise} ${684 + inset} ${875 - rise} ${684 + inset} ${875 - rise}`,
      index,
      opacity: 0.08 + index * 0.013,
      width: 0.55 + index * 0.032,
    }
  })
}

const PATH_LAYERS = [makePaths(1), makePaths(-1)]

export function AuthAtmosphere() {
  const reduceMotion = useReducedMotion()

  return (
    <div className="auth-atmosphere" aria-hidden="true" data-motion={reduceMotion ? 'reduced' : 'full'}>
      <div className="auth-ambient" />
      {PATH_LAYERS.map((paths, layerIndex) => (
        <m.div
          className={`auth-path-layer auth-path-layer-${layerIndex + 1}`}
          key={layerIndex}
          animate={reduceMotion ? undefined : {
            x: layerIndex === 0 ? ['-1.5%', '1.5%', '-1.5%'] : ['1.2%', '-1.8%', '1.2%'],
            y: layerIndex === 0 ? ['-1%', '1.2%', '-1%'] : ['1%', '-1.3%', '1%'],
            scale: [1, 1.018, 1],
          }}
          transition={{
            duration: layerIndex === 0 ? 28 : 34,
            ease: 'easeInOut',
            repeat: Number.POSITIVE_INFINITY,
          }}
        >
          <svg viewBox="0 0 696 316" fill="none" focusable="false" preserveAspectRatio="xMidYMid slice">
            {paths.map((path) => {
              const animated = path.index % 4 === 0
              const shared = {
                className: `auth-path${animated ? ' auth-path-active' : ''}`,
                d: path.d,
                stroke: 'currentColor',
                strokeLinecap: 'round' as const,
                strokeOpacity: path.opacity,
                strokeWidth: path.width,
                vectorEffect: 'non-scaling-stroke' as const,
              }
              if (!animated) return <path key={path.index} {...shared} />
              return (
                <m.path
                  key={path.index}
                  {...shared}
                  initial={reduceMotion ? false : { opacity: path.opacity * 0.7, pathLength: 0.32 }}
                  animate={reduceMotion ? { opacity: path.opacity, pathLength: 1, pathOffset: 0 } : {
                    opacity: [path.opacity * 0.55, path.opacity, path.opacity * 0.55],
                    pathLength: [0.32, 1, 0.46],
                    pathOffset: [0, 0.18, 0.72],
                  }}
                  transition={{
                    duration: 18 + path.index * 0.45 + layerIndex * 2.5,
                    ease: 'linear',
                    repeat: Number.POSITIVE_INFINITY,
                  }}
                />
              )
            })}
          </svg>
        </m.div>
      ))}
    </div>
  )
}
