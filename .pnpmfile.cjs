'use strict'

function readPackage(pkg) {
  if (pkg.name !== 'tus-js-client' || pkg.version !== '4.3.1') return pkg

  const dependencies = { ...pkg.dependencies }
  delete dependencies['combine-errors']
  return { ...pkg, dependencies }
}

module.exports = { hooks: { readPackage } }
