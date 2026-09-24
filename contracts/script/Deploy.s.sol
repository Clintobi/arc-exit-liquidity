// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {ArcFlagRegistry} from "../src/ArcFlagRegistry.sol";

/// Deploy ArcFlagRegistry to Arc mainnet (chain 5042).
///
/// Arc pays gas in USDC, so the deployer address needs a USDC balance on Arc
/// before this will run — there is no native-token faucet path on mainnet, and
/// the microgrant rules out testnet-only builds.
///
///   forge script script/Deploy.s.sol:Deploy \
///     --rpc-url https://rpc.mainnet.arc.io \
///     --private-key $PK --broadcast
///
/// Drop --broadcast for a dry run that still prints the gas it would burn.
contract Deploy is Script {
    function run() external returns (ArcFlagRegistry reg) {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(pk);

        console.log("chain id        ", block.chainid);
        console.log("deployer        ", deployer);
        console.log("balance (wei)   ", deployer.balance);

        vm.startBroadcast(pk);
        reg = new ArcFlagRegistry();
        vm.stopBroadcast();

        console.log("ArcFlagRegistry ", address(reg));
        console.log("owner           ", reg.owner());
    }
}
