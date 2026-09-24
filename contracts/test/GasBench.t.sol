// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {ArcFlagRegistry} from "../src/ArcFlagRegistry.sol";

/// Measures what a real publishing round costs, not a toy one.
contract GasBench is Test {
    ArcFlagRegistry reg;
    function setUp() public { reg = new ArcFlagRegistry(); }

    function _batch(uint256 n) internal {
        address[] memory t = new address[](n);
        uint8[] memory f = new uint8[](n);
        uint32[] memory p = new uint32[](n);
        uint32[] memory tr = new uint32[](n);
        uint32[] memory mf = new uint32[](n);
        for (uint256 i; i < n; ++i) {
            t[i] = address(uint160(0x100000 + i));
            f[i] = 1; p[i] = 3; tr[i] = 120; mf[i] = 10_000;
        }
        uint256 g = gasleft();
        reg.setFlagsBatch(t, f, p, tr, mf, 22_357_859);
        console.log("batch size", n, "gas", g - gasleft());
    }

    function test_gas_batch_50()  public { _batch(50); }
    function test_gas_batch_155() public { _batch(155); }   // the impostor set
    function test_gas_batch_300() public { _batch(300); }
    function test_gas_rewrite_155() public {
        _batch(155);            // first write: cold storage
        _batch(155);            // republish: warm slots, the steady-state cost
    }
}
