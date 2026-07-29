# @pathlab/viewer-ui

The shared PathLab Viewer Canvas Focus shell. PathLab Viewer is the design
authority; trusted desktop clients consume an immutable released version
instead of copying its interface.

The package contains code-native navigation, viewer shell, inspector, queue,
theme tokens and the complete manual annotation-tool inventory. Application
adapters remain responsible for data, authentication and persistence. The
package exports typed contracts for slide sources, library and viewer
commands, annotations, themes, accounts, and capabilities so Viewer can use
server adapters while Forge uses paired local-desktop adapters.
